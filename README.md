# Ágora

Trabalho pŕatico da Disciplina DCC094 @ UFMG no semestre de 2026/1

## Membros do Projeto
| Nome | Papel |
|---------------|-------|
| Gabriel Vieira  | Full Stack |
| Gustavo Mattos Lopes | Full Stack |
| Luis Henrique Gomes Higino  | Full Stack |
| Matheus Torres Prates | Full Stack |

## Objetivo do Sistema
Nosso sistema visa fornecer uma plataforma virtual de aprendizagem completa e integrada, projetada para simplificar a criação, organização e gerenciamento de cursos em um ambiente totalmente digital. A plataforma permite que professores disponibilizem conteúdos, atividades e avaliações de forma facilitada, além de oferecer recursos interativos como fóruns, quizzes, tarefas e chats em prol do engajamento dos alunos. Os estudantes, por sua vez, podem acessar os materiais, submeter os exercícios, participar das discussões e acompanhar seu progresso e desempenho em cada curso que está realizando, com uma visão geral de todas as disciplinas em que estão matriculados. O objetivo final do sistema é criar um ambiente digital que promove uma experiência educacional moderna, intuitiva, eficiente e personalizada.

## Tecnologias Utilizadas
- **Linguagens:** HTML, CSS, JavaScript, JSX, Python
- **Frameworks:** React, Django
- **Banco de Dados:** SQLite
- **Agentes de IA:** Claude Code, Codex

## Dataset de demonstração

Para popular o banco com dados fictícios, use:

```bash
python manage.py migrate
python manage.py seed --reset --seed 1234 --password demo123
```

- Usuários criados: `demo_prof_ana`, `demo_prof_carlos`, `demo_aluno_joao`, `demo_aluna_maria`, `demo_aluno_pedro`, `demo_aluna_luiza`, `demo_aluno_rodrigo`, `demo_aluna_camila`, `demo_aluno_felipe`, `demo_aluna_bruna`, `demo_aluno_igor`
- Cursos criados: códigos começando com `DEMO-`
- O `--reset` remove **apenas** dados de demonstração (usuários `demo_*` e cursos `DEMO-*`) antes de recriar.
- O `--seed` permite repetir as mesmas variações textuais entre execuções.

## Histórias de Usuário
0. Como estudante, quero fazer login para acessar meus cursos e todos os recursos disponíveis de cada um deles.
1. Como estudante, quero realizar tarefas e atividades para que meu progresso seja registrado automaticamente.
2. Como estudante, quero monitorar minhas notas em tempo real para acompanhar meu desempenho.
3. Como estudante, quero acessar um painel com cursos disponíveis e me matricular neles.
4. Como professor, quero criar cursos digitais para disponibilizar conteúdos, materiais de apoio e atividades.
5. Como professor, quero criar atividades online para que os alunos possam entregar e ser avaliados.
6. Como professor, quero configurar datas de entrega e prazos para tarefas e atividades.
7. Como professor, quero consultar e atualizar o desempenho dos alunos, visualizando um relatório com suas atividades entregues e notas.
