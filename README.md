<img src="workstation.svg" width="96" align="right" alt="">

# All-in-One Workstation

App de foco para desktop Linux (GTK 4 + Python) que junta, num lugar só, timer Pomodoro, lista de tarefas e notas, com o contador sempre visível na barra superior do GNOME.

Começou como um clone do tomato-timer.com e foi crescendo.

## Funcionalidades

- **Timer**: modos Pomodoro, Short Break e Long Break, com tempos configuráveis
- **Meta diária**: contador de pomodoros feitos no dia com barra de progresso
- **Pomodoros por semana**: gráfico de barras das últimas 8 semanas com os pomodoros concluídos
- **Time Log**: histórico das sessões (início, fim e o que você fez em cada uma)
- **Alarme**: 6 sons sintetizados na hora (sem arquivos de áudio) e volume ajustável (Mute, 10%–100%)
- **Notificações** de desktop quando o tempo acaba e auto start opcional do próximo ciclo
- **Tasks**: lista de tarefas com projetos, prioridades e datas. Um clique inicia um pomodoro focado na tarefa
- **Board**: cada projeto pode ser visto em lista ou em board (kanban), com seções como colunas e arrastar e soltar para mover entre colunas ou reordenar dentro delas
- **Sub-tasks**: tarefas dentro de tarefas, em quantos níveis quiser. Concluir a tarefa conclui as sub-tasks
- **Copiar para o Claude**: o botão 🤖 de uma tarefa copia ela e todas as sub-tasks como um plano de implementação pronto para colar no Claude
- **Tema Dracula**: visual no estilo do Todoist com as cores do Dracula, inclusive no timer da barra superior
- **Tema PC anos 2000** (opcional, em Options → Theme): visual de Windows 98 vaporwave, com botões 3D, fonte pixelada VT323, timer num monitor CRT, tela de boot de BIOS e cliques e bipes retrô
- **Notes**: editor de texto visual com barra de ferramentas (títulos, negrito, itálico, sublinhado, riscado, destaque, código, listas e checklist), sem precisar escrever Markdown. Por baixo, cada nota é salva como `.md` em `~/Documentos/Workstation Notes`
- **Notas do Claude**: arquivos `.md` que o Claude grava em `~/Documentos/Workstation Notes/Claude` aparecem sozinhos na aba Notes, agrupados por tema (cada subpasta vira um grupo 🤖), somente leitura (tabelas alinhadas). Notas editadas fora do app também recarregam sozinhas
- **Abas opcionais**: em Options → Tabs dá para esconder as abas Tasks e Notes (o Timer fica sempre visível)
- **Tasks + Claude**: cada task pode ter um repo (ou herdar o do projeto) e o ticket do Jira é detectado no título ou na descrição. O 🤖 copia o plano com os ids, e o Claude dá notícias pela CLI (`all-in-one-workstation task show|done|note|add <id>`); o app recarrega sozinho. O botão **✨ Plan** pede a um agente Sonnet só leitura uma sugestão de sub-tasks
- **Todoist**: o botão **⟳ Sync with Todoist** sincroniza projetos, seções e tasks nos dois sentidos (Urgent = P1)
- **Barra superior**: extensão do GNOME Shell que mostra `⏰ MM:SS` com a cor do modo atual. Clicar nela abre o app

## Atalhos

| Tecla   | Ação         |
|---------|--------------|
| `Space` | Start / Stop |
| `Alt+P` | Pomodoro     |
| `Alt+S` | Short Break  |
| `Alt+L` | Long Break   |
| `Alt+R` | Reset        |
| `Alt+1` `Alt+2` `Alt+3` | Abas Timer, Tasks e Notes |

## Requisitos

- Python 3 com PyGObject e GTK 4 (`sudo apt install python3-gi gir1.2-gtk-4.0`)
- GNOME Shell 45+ para o timer na barra superior (opcional)
- `pw-play`, `paplay` ou `aplay` para o som e `notify-send` para as notificações

## Instalação

```sh
./install.sh
```

Instala em `~/.local` (app, ícone, entrada no menu, comando `all-in-one-workstation` e a extensão da barra). Se você tinha a versão antiga (Tomato Timer), o install migra suas configurações, tarefas e notas e remove a instalação antiga. No Wayland, faça logout/login para a extensão aparecer na primeira vez.

Para remover: `./uninstall.sh`

## Onde ficam os dados

| O quê                  | Onde                                            |
|------------------------|-------------------------------------------------|
| Preferências e log     | `~/.config/all-in-one-workstation/state.json`   |
| Tarefas                | `~/.config/all-in-one-workstation/tasks.json`   |
| Notas                  | `~/Documentos/Workstation Notes/*.md`           |
| Estado para a barra    | `$XDG_RUNTIME_DIR/all-in-one-workstation/panel.json` |

## Estrutura

```
workstation.py           janela principal, timer, sons e opções
workstation_tasks.py     aba Tasks
workstation_notes.py     aba Notes
workstation_theme.py     paleta e CSS do tema Dracula
workstation_retro.py     tema opcional PC anos 2000 (CSS, tela de boot, scanlines)
fonts/                   fonte pixelada VT323 (licença OFL)
panel-extension/         extensão do GNOME Shell (barra superior)
install.sh/uninstall.sh  instalação local em ~/.local
```
