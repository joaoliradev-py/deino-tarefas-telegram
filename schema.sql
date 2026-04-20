CREATE TABLE IF NOT EXISTS tarefas (
    id SERIAL PRIMARY KEY,                             -- ID único
    titulo VARCHAR(255) NOT NULL,                      -- Título da tarefa
    descricao TEXT,                                    -- Descrição da tarefa
    deadline VARCHAR(50),                              -- Data Limite / Prazo
    concluida BOOLEAN DEFAULT FALSE,                   -- Estado da tarefa
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
