-- 3. Tabela de Tarefas (To-Do List)
CREATE TABLE IF NOT EXISTS tarefas (
    id SERIAL PRIMARY KEY,                             -- ID único
    titulo VARCHAR(255) NOT NULL,                      -- Título da tarefa
    descricao TEXT,                                    -- Descrição da tarefa
    deadline VARCHAR(50),                              -- Data Limite / Prazo (Texto)
    deadline_date DATE,                                -- Data Limite (Objeto Date para lembretes)
    chat_id BIGINT,                                    -- ID do chat para enviar lembretes
    concluida BOOLEAN DEFAULT FALSE,                   -- Estado da tarefa
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- COMANDOS PARA ATUALIZAR TABELA EXISTENTE:
-- ALTER TABLE tarefas ADD COLUMN chat_id BIGINT;
-- ALTER TABLE tarefas ADD COLUMN deadline_date DATE;