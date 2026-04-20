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
MY_CHAT_ID = os.getenv("MY_CHAT_ID")

# Configuração de Logs
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Inicializa cliente Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def parse_task_message(text):
    """
    Analisa a mensagem para extrair apenas o que o schema original permite.
    Colunas: titulo, descricao, deadline
    """
    task_data = {
        "titulo": None,
        "descricao": None,
        "deadline": None
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
        task_data["deadline"] = deadline_match.group(1).strip()
        
    # 2. FALLBACK: Título pela primeira linha
    if not task_data["titulo"]:
        lines = text.split('\n')
        if lines:
            task_data["titulo"] = lines[0].strip()
            if len(lines) > 1 and not task_data["descricao"]:
                # Se não usou prefixos, o resto vira descrição
                # E tentamos ver se a última linha parece um prazo
                possible_deadline = lines[-1].strip()
                if any(k in possible_deadline.lower() for k in ["dia", "prazo", "vence", "até", "ate", "/"]):
                    task_data["deadline"] = possible_deadline
                    task_data["descricao"] = "\n".join(lines[1:-1]).strip()
                else:
                    task_data["descricao"] = "\n".join(lines[1:]).strip()
        
    return task_data

async def verificar_prazos(context: ContextTypes.DEFAULT_TYPE):
    """
    Função diária que busca lembretes.
    Como não temos a coluna DATE no banco, filtramos via código Python.
    """
    if not MY_CHAT_ID:
        logging.warning("MY_CHAT_ID não configurado. Lembretes desativados.")
        return

    logging.info("Iniciando verificação de prazos (Lógica Python)...")
    hoje = datetime.now()
    alerta_data_alvo = (hoje + timedelta(days=3)).date()
    
    try:
        # Busca TODAS as tarefas não concluídas
        response = supabase.table("tarefas").select("*").eq("concluida", False).execute()
        tarefas = response.data
        
        for tarefa in tarefas:
            deadline_text = tarefa.get("deadline")
            if not deadline_text:
                continue
                
            # Tenta interpretar o texto do prazo como uma data real
            parsed_date = dateparser.parse(
                deadline_text, 
                settings={'RELATIVE_BASE': hoje, 'PREFER_DATES_FROM': 'future', 'DATE_ORDER': 'DMY'}
            )
            
            # Se bater com a data de daqui a 3 dias
            if parsed_date and parsed_date.date() == alerta_data_alvo:
                mensagem = (
                    f"⚠️ **LEMBRETE DE PRAZO!**\n\n"
                    f"A tarefa **{tarefa['titulo']}** vence em 3 dias!\n"
                    f"📅 Prazo original: {deadline_text}\n\n"
                    f"Não esqueça de finalizá-la! 😉"
                )
                await context.bot.send_message(chat_id=MY_CHAT_ID, text=mensagem, parse_mode='Markdown')
                
    except Exception as e:
        logging.error(f"Erro na verificação: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    chat_id = update.message.chat_id
    
    if not text:
        return

    # Mostrar ID se não estiver configurado
    if not MY_CHAT_ID:
        await update.message.reply_text(f"🆔 Seu ID é: `{chat_id}`\nConfigure MY_CHAT_ID no seu .env!", parse_mode='Markdown')

    task_data = parse_task_message(text)

    try:
        # Insere apenas campos originais (titulo, descricao, deadline)
        supabase.table("tarefas").insert(task_data).execute()
        
        msg = (
            f"✅ **Tarefa cadastrada!**\n\n"
            f"📌 **T: ** {task_data['titulo']}\n"
            f"📝 **D: ** {task_data['descricao'] or '---'}\n"
            f"📅 **P: ** {task_data['deadline'] or '---'}"
        )
        await update.message.reply_text(msg, parse_mode='Markdown')
        
    except Exception as e:
        logging.error(f"Erro no Supabase: {e}")
        await update.message.reply_text(f"❌ Erro ao salvar: {str(e)}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🚀 Bot Ativo!\nSeu ID: `{update.message.chat_id}`", parse_mode='Markdown')

if __name__ == '__main__':
    if not all([TELEGRAM_TOKEN, SUPABASE_URL, SUPABASE_KEY]):
        print("⚠️ Verifique suas credenciais no .env")
    else:
        application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        application.add_handler(MessageHandler(filters.COMMAND & filters.Regex(r'/start'), start))
        application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
        
        # Agenda diariamente às 09:00 AM
        application.job_queue.run_daily(verificar_prazos, time=time(hour=9, minute=0))
        
        print("🚀 Bot rodando com Schema Original!")
        application.run_polling()
