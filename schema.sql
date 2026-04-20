-- 3. Tabela de Tarefas (To-Do List)
CREATE TABLE IF NOT EXISTS tarefas (
    id SERIAL PRIMARY KEY,                             -- ID único
    titulo VARCHAR(255) NOT NULL,                      -- Título da tarefa
    descricao TEXT,                                    -- Descrição da tarefa
    deadline VARCHAR(50),                              -- Data Limite / Prazo (Texto)
    deadline_date DATE,                                -- Data Limite (Objeto Date para lembretes)
    concluida BOOLEAN DEFAULT FALSE,                   -- Estado da tarefa
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- COMANDO PARA ATUALIZAR TABELA EXISTENTE:
-- (Apenas deadline_date é necessário para o bot funcionar agora)
-- ALTER TABLE tarefas ADD COLUMN IF NOT EXISTS deadline_date DATE;