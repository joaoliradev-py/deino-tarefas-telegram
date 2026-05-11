import os
import logging
import re
import dateparser
from datetime import datetime, date, timedelta, time
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, filters
from supabase import create_client, Client

# Carrega variáveis de ambiente
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
MY_CHAT_ID = os.getenv("MY_CHAT_ID")

# Configuração de Logs em Português
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("DeinoBot")

# Cliente Supabase (inicializado no bloco principal)
supabase: Client = None

def parse_task_message(text):
    """
    Analisa a mensagem para extrair: titulo, descricao, deadline.
    Formata a data para dd/mm/yy (padrão do App Desktop).
    """
    task_data = {
        "titulo": "Nova Tarefa",
        "descricao": "",
        "deadline": datetime.now().strftime("%Y-%m-%d")  # Formato ISO para o tipo DATE do Supabase
    }
    
    # 1. TENTA EXTRAIR POR PREFIXOS (Título:, Descrição:, Prazo:)
    titulo_match = re.search(r"(?i)(?:Título|Titulo):\s*(.*)", text)
    desc_match = re.search(r"(?i)(?:Descrição|Descricao):\s*(.*)", text)
    deadline_match = re.search(r"(?i)(?:Deadline|Prazo|Para):\s*(.*)", text)

    if titulo_match:
        task_data["titulo"] = titulo_match.group(1).strip()
    if desc_match:
        task_data["descricao"] = desc_match.group(1).strip()
    if deadline_match:
        raw_date = deadline_match.group(1).strip()
        parsed_date = dateparser.parse(
            raw_date,
            languages=['pt'],  # Força o parsing em Português
            settings={
                'DATE_ORDER': 'DMY',
                'PREFER_DATES_FROM': 'future',
            }
        )
        if parsed_date:
            task_data["deadline"] = parsed_date.strftime("%Y-%m-%d")  # ISO para o Supabase
        else:
            task_data["deadline"] = datetime.now().strftime("%Y-%m-%d")  # Fallback: hoje

    # 2. SE NÃO USOU PREFIXOS, USA LÓGICA DE LINHAS
    if not titulo_match:
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        if lines:
            task_data["titulo"] = lines[0]
            if len(lines) > 1 and not desc_match:
                # Tenta ver se a última linha parece uma data
                possible_date = dateparser.parse(
                    lines[-1],
                    languages=['pt'],  # Força o parsing em Português
                    settings={
                        'DATE_ORDER': 'DMY',
                        'PREFER_DATES_FROM': 'future',
                    }
                )
                if possible_date and len(lines) > 1:
                    task_data["deadline"] = possible_date.strftime("%Y-%m-%d")  # ISO para o Supabase
                    task_data["descricao"] = " ".join(lines[1:-1])
                else:
                    task_data["descricao"] = " ".join(lines[1:])

    # Limita descrição a 200 caracteres (padrão do App)
    if len(task_data["descricao"]) > 200:
        task_data["descricao"] = task_data["descricao"][:197] + "..."
        
    return task_data

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start"""
    user_id = update.effective_chat.id
    msg = (
        "👋 **Olá! Eu sou o assistente do Deino Tarefas!**\n\n"
        "Posso cadastrar tarefas direto no seu app desktop.\n\n"
        "📋 **Formato completo:**\n"
        "`Título: Estudar Python`\n"
        "`Descrição: Ver aula sobre APIs REST`\n"
        "`Prazo: amanhã`\n\n"
        "⚡ **Formato rápido (sem prefixos):**\n"
        "`Estudar Python`\n"
        "`Ver aula sobre APIs REST`\n"
        "`amanhã`\n"
        "_1ª linha = título, meio = descrição, última = prazo_\n\n"
        "⚠️ Descrição: máximo 200 caracteres.\n\n"
        "**Comandos:**\n"
        "/tarefas - Lista tarefas pendentes\n"
        "/concluir ID - Marca como feita\n"
        f"\n🆔 Seu ID: `{user_id}`"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /tarefas"""
    logger.info(f"Usuário {update.effective_chat.id} solicitou lista de tarefas.")
    try:
        # Busca tarefas não concluídas
        res = supabase.table("tarefas").select("*").eq("concluida", False).order("id", desc=True).limit(10).execute()
        tarefas = res.data
        
        if not tarefas:
            await update.message.reply_text("📭 Nenhuma tarefa pendente! Bom trabalho.")
            return

        msg = "📋 **Suas últimas 10 tarefas pendentes:**\n\n"
        for t in tarefas:
            msg += f"🔹 `ID {t['id']}`: **{t['titulo']}**\n"
            msg += f"   📅 {t['deadline']}\n\n"
        
        msg += "Para concluir, use: `/concluir ID`"
        await update.message.reply_text(msg, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Erro ao listar: {e}")
        await update.message.reply_text("❌ Erro ao buscar tarefas no banco.")

async def verificar_prazos(context: ContextTypes.DEFAULT_TYPE):
    """
    Roda diariamente às 09:00 e avisa sobre tarefas com prazo em 3 dias.
    Filtra direto no Supabase usando o tipo DATE nativo.
    """
    if not MY_CHAT_ID:
        logger.warning("MY_CHAT_ID não configurado. Lembretes desativados.")
        return

    alerta_data = (date.today() + timedelta(days=3)).isoformat()  # ex: '2026-05-14'
    logger.info(f"Verificando tarefas com prazo em: {alerta_data}")

    try:
        res = supabase.table("tarefas") \
            .select("*") \
            .eq("concluida", False) \
            .eq("deadline", alerta_data) \
            .execute()

        tarefas = res.data
        if not tarefas:
            logger.info("Nenhuma tarefa com prazo em 3 dias hoje.")
            return

        for tarefa in tarefas:
            # Formata data para exibição: YYYY-MM-DD → DD/MM/AAAA
            try:
                d = date.fromisoformat(tarefa['deadline'])
                deadline_display = d.strftime("%d/%m/%Y")
            except Exception:
                deadline_display = tarefa['deadline']

            mensagem = (
                f"⚠️ **LEMBRETE DE PRAZO!**\n\n"
                f"A tarefa **{tarefa['titulo']}** vence em 3 dias!\n"
                f"📅 Prazo: {deadline_display}\n\n"
                f"Não esqueça de finalizá-la! 💪"
            )
            await context.bot.send_message(
                chat_id=MY_CHAT_ID,
                text=mensagem,
                parse_mode='Markdown'
            )
            logger.info(f"Lembrete enviado para tarefa '{tarefa['titulo']}' (prazo: {alerta_data})")

    except Exception as e:
        logger.error(f"Erro na verificação de prazos: {e}")

async def done_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /concluir ID"""
    if not context.args:
        await update.message.reply_text("⚠️ Informe o ID. Ex: `/concluir 12`", parse_mode='Markdown')
        return

    task_id = context.args[0]
    try:
        supabase.table("tarefas").update({"concluida": True}).eq("id", task_id).execute()
        await update.message.reply_text(f"✅ Tarefa `{task_id}` marcada como concluída!", parse_mode='Markdown')
        logger.info(f"Tarefa {task_id} concluída via Telegram.")
    except Exception as e:
        logger.error(f"Erro ao concluir {task_id}: {e}")
        await update.message.reply_text("❌ Erro ao atualizar tarefa. Verifique o ID.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lida com mensagens de texto (criação de tarefas)"""
    text = update.message.text
    if not text: return

    logger.info(f"Recebida mensagem para nova tarefa: {text[:30]}...")
    task_data = parse_task_message(text)

    try:
        # Insere no Supabase
        supabase.table("tarefas").insert(task_data).execute()

        # Formata a data para exibição amigável: YYYY-MM-DD → DD/MM/AAAA
        try:
            from datetime import date
            d = date.fromisoformat(task_data['deadline'])
            deadline_display = d.strftime("%d/%m/%Y")
        except Exception:
            deadline_display = task_data['deadline']

        msg = (
            "✨ **Tarefa Salva!**\n"
            f"📌 **{task_data['titulo']}**\n"
            f"📅 Prazo: `{deadline_display}`\n"
            f"📝 {task_data['descricao'] or 'Sem descrição'}"
        )
        await update.message.reply_text(msg, parse_mode='Markdown')
        logger.info(f"Tarefa '{task_data['titulo']}' salva com sucesso.")
    except Exception as e:
        logger.error(f"Erro ao salvar tarefa: {e}")
        await update.message.reply_text("❌ Tive um problema ao salvar no banco de dados.")

if __name__ == '__main__':
    if not all([TELEGRAM_TOKEN, SUPABASE_URL, SUPABASE_KEY]):
        logger.error("❌ Variáveis de ambiente faltando no .env! Verifique TELEGRAM_TOKEN, SUPABASE_URL e SUPABASE_KEY.")
    else:
        # Cria o cliente Supabase aqui, depois de validar as variáveis
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("✅ Conexão com Supabase estabelecida.")

        app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

        # Handlers de comandos e mensagens
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("tarefas", list_tasks))
        app.add_handler(CommandHandler("concluir", done_task))
        app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

        # Job diário de lembrete às 09:00
        if MY_CHAT_ID:
            app.job_queue.run_daily(
                verificar_prazos,
                time=time(hour=11, minute=0),  # 11:00 UTC = 08:00 Brasília (UTC-3)
                name="lembrete_prazo"
            )
            logger.info("🔔 Lembrete diário agendado para 08:00 (horário de Brasília).")
        else:
            logger.warning("⚠️ MY_CHAT_ID não definido — lembretes desativados.")

        logger.info("🚀 Bot do Deino iniciado e pronto para agir!")
        app.run_polling()
