import os
import logging
import re
import dateparser
from datetime import datetime, time, timedelta
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, JobQueue
from supabase import create_client, Client

# Carrega variáveis de ambiente
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
MY_CHAT_ID = os.getenv("MY_CHAT_ID") # Novo: ID fixo para lembretes

# Configuração de Logs
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Inicializa cliente Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def parse_task_message(text):
    """
    Analisa a mensagem para extrair título, descrição e deadline.
    """
    task_data = {
        "titulo": None,
        "descricao": None,
        "deadline": None,
        "deadline_date": None
    }
    
    # 1. TENTA EXTRAIR POR PREFIXOS
    titulo_match = re.search(r"(?i)(?:Título|Titulo):\s*(.*)", text)
    desc_match = re.search(r"(?i)(?:Descrição|Descricao):\s*(.*)", text)
    deadline_match = re.search(r"(?i)(?:Deadline|Prazo):\s*(.*)", text)

    if titulo_match:
        task_data["titulo"] = titulo_match.group(1).strip()
    if desc_match:
        task_data["descricao"] = desc_match.group(1).strip()
    if deadline_match:
        deadline_text = deadline_match.group(1).strip()
        task_data["deadline"] = deadline_text
        
        # Tenta interpretar a data usando dateparser
        parsed_date = dateparser.parse(
            deadline_text, 
            settings={'RELATIVE_BASE': datetime.now(), 'PREFER_DATES_FROM': 'future', 'DATE_ORDER': 'DMY'}
        )
        if parsed_date:
            task_data["deadline_date"] = parsed_date.date().isoformat()
            
    # 2. FALLBACK: Se não achar título por prefixo, usa a primeira linha
    if not task_data["titulo"]:
        lines = text.split('\n')
        if lines:
            task_data["titulo"] = lines[0].strip()
            if len(lines) > 1 and not task_data["descricao"]:
                task_data["descricao"] = "\n".join(lines[1:]).strip()
        
    return task_data

async def verificar_prazos(context: ContextTypes.DEFAULT_TYPE):
    """
    Função que roda diariamente buscando tarefas que vencem em 3 dias.
    Envia lembretes para o MY_CHAT_ID fixo.
    """
    if not MY_CHAT_ID:
        logging.warning("MY_CHAT_ID não configurado. Lembretes automáticos desativados.")
        return

    logging.info("Iniciando verificação diária de prazos...")
    alerta_data = (datetime.now() + timedelta(days=3)).date().isoformat()
    
    try:
        # Busca tarefas não concluídas que vencem em 3 dias
        response = supabase.table("tarefas").select("*").eq("concluida", False).eq("deadline_date", alerta_data).execute()
        tarefas_pendentes = response.data
        
        if not tarefas_pendentes:
            logging.info("Nenhuma tarefa com prazo de 3 dias encontrada.")
            return

        for tarefa in tarefas_pendentes:
            mensagem = (
                f"⚠️ **LEMBRETE DE PRAZO!**\n\n"
                f"A tarefa **{tarefa['titulo']}** vence em 3 dias!\n"
                f"📅 Prazo: {tarefa['deadline'] or tarefa['deadline_date']}\n\n"
                f"Não esqueça de finalizá-la! 😉"
            )
            # Envia diretamente para o ID fixo configurado
            await context.bot.send_message(chat_id=MY_CHAT_ID, text=mensagem, parse_mode='Markdown')
                
    except Exception as e:
        logging.error(f"Erro na verificação de prazos: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    chat_id = update.message.chat_id
    
    if not text:
        return

    # Check if MY_CHAT_ID is missing and inform the user
    if not MY_CHAT_ID:
        await update.message.reply_text(
            f"👋 Olá! Vi sua mensagem, mas ainda não configurei o seu ID para enviar lembretes.\n\n"
            f"🆔 Seu ID é: `{chat_id}`\n\n"
            f"Por favor, adicione essa linha ao seu arquivo `.env`:\n"
            f"`MY_CHAT_ID={chat_id}`"
        , parse_mode='Markdown')

    task_data = parse_task_message(text)
    # IMPORTANTE: Removido 'chat_id' da persistência no banco para evitar erro de coluna

    if not task_data["titulo"]:
        await update.message.reply_text("❌ Não consegui identificar o título da tarefa. Tente usar 'Título: ...'")
        return

    try:
        # Insere no Supabase
        supabase.table("tarefas").insert(task_data).execute()
        
        msg_confirmacao = (
            f"✅ **Tarefa cadastrada!**\n\n"
            f"📌 **Título:** {task_data['titulo']}\n"
            f"📝 **Descrição:** {task_data['descricao'] or 'N/A'}\n"
            f"📅 **Deadline:** {task_data['deadline'] or 'N/A'}"
        )
        
        if task_data["deadline_date"]:
            msg_confirmacao += f"\n\n🔔 **Lembrete ativado para 3 dias antes!**"
        elif task_data["deadline"]:
             msg_confirmacao += "\n\n⚠️ **Nota:** Não consegui criar um lembrete automático para este formato de data."

        await update.message.reply_text(msg_confirmacao, parse_mode='Markdown')
        
    except Exception as e:
        logging.error(f"Erro ao salvar no Supabase: {e}")
        await update.message.reply_text(f"❌ Erro ao salvar a tarefa: {str(e)}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    await update.message.reply_text(
        f"👋 Olá! Eu sou seu bot de rotina.\n\n"
        f"🆔 Seu ID é: `{chat_id}` (Se ainda não colocou no `.env`, faça isso agora!)\n\n"
        "Envie uma tarefa assim:\n"
        "Título: Academia\n"
        "Descrição: Treino de perna\n"
        "Deadline: Amanhã às 18h\n\n"
        "Eu te avisarei 3 dias antes do prazo! 🔔",
        parse_mode='Markdown'
    )

if __name__ == '__main__':
    if not all([TELEGRAM_TOKEN, SUPABASE_URL, SUPABASE_KEY]):
        print("⚠️ Erro: Credenciais não configuradas no .env")
    else:
        application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        
        application.add_handler(MessageHandler(filters.COMMAND & filters.Regex(r'/start'), start))
        application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
        
        # Agenda o Job Diário às 09:00 AM
        job_queue = application.job_queue
        job_queue.run_daily(verificar_prazos, time=time(hour=9, minute=0))
        
        print("🚀 Bot Centralizado iniciado! Aguardando mensagens...")
        application.run_polling()
