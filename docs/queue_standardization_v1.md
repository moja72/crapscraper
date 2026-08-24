# Fila canônica v1

As filas **Atualizar** e **Adicionar** compartilham a mesma hierarquia visual e operacional:

1. Cabeçalho/accordion com título e resumo.
2. Descrição e botão de gerenciamento de listas.
3. Lista ativa e checkpoint.
4. Três ações principais da fila.
5. Cards de estado clicáveis.
6. Busca, Estado e Atualizar.
7. Contagem de resultados e itens por página.
8. Seleção de página, todo resultado, limpeza da seleção e ações em lote.
9. Jobs em cards com estado, progresso e Detalhes.
10. Paginação Anterior / Página / Próxima.

A implementação reutiliza os IDs e elementos funcionais existentes para preservar listeners e contratos do backend. Ao limpar concluídos da fila visual de Atualizar, o estado final e o histórico operacional são preservados.
