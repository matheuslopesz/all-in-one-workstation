<img src="workstation.svg" width="96" align="right" alt="">

# All-in-One Workstation

App de foco para desktop Linux (GTK 4 + Python) que junta, num lugar só, timer Pomodoro, lista de tarefas e notas, com o contador sempre visível na barra superior do GNOME.

Começou como um clone do tomato-timer.com e foi crescendo.

## Funcionalidades

- **Timer**: modos Pomodoro, Short Break e Long Break, com tempos configuráveis
- **Meta diária**: contador de pomodoros feitos no dia com barra de progresso
- **Time Log**: histórico das sessões (início, fim e o que você fez em cada uma)
- **Alarme**: 6 sons sintetizados na hora (sem arquivos de áudio) e volume ajustável (Mute, 10%–100%)
- **Notificações** de desktop quando o tempo acaba e auto start opcional do próximo ciclo
- **Tasks**: lista de tarefas com projetos, prioridades e datas. Um clique inicia um pomodoro focado na tarefa
- **Notes**: notas em Markdown salvas em `~/Documentos/Workstation Notes`
- **Barra superior**: extensão do GNOME Shell que mostra `⏰ MM:SS` com a cor do modo atual. Clicar nela abre o app

## Atalhos

| Tecla   | Ação         |
|---------|--------------|
| `Space` | Start / Stop |
| `Alt+P` | Pomodoro     |
| `Alt+S` | Short Break  |
| `Alt+L` | Long Break   |
| `Alt+R` | Reset        |

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
panel-extension/         extensão do GNOME Shell (barra superior)
install.sh/uninstall.sh  instalação local em ~/.local
```
