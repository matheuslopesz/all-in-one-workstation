# 🍅 Tomato Timer

Timer Pomodoro nativo para desktop Linux (GTK 4 + Python), inspirado no tomato-timer.com, com tarefas, notas e um contador na barra superior do GNOME.

## Funcionalidades

- **Timer**: modos Pomodoro, Short Break e Long Break, com tempos configuráveis
- **Meta diária**: contador de pomodoros feitos no dia com barra de progresso
- **Time Log**: histórico das sessões (início, fim e o que você fez em cada uma)
- **Alarme**: 6 sons sintetizados na hora (sem arquivos de áudio) e volume ajustável (Mute, 10%–100%)
- **Notificações** de desktop quando o tempo acaba e auto start opcional do próximo ciclo
- **Tasks**: lista de tarefas com projetos, prioridades e datas. Um clique inicia um pomodoro focado na tarefa
- **Notes**: notas em Markdown salvas em `~/Documentos/Tomato Notes`
- **Barra superior**: extensão do GNOME Shell que mostra `🍅 MM:SS` com a cor do modo atual. Clicar nela abre o app

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

Instala em `~/.local` (app, ícone, entrada no menu e a extensão da barra). No Wayland, faça logout/login para a extensão aparecer na primeira vez.

Para remover: `./uninstall.sh`

## Onde ficam os dados

| O quê                  | Onde                                            |
|------------------------|-------------------------------------------------|
| Preferências e log     | `~/.config/tomato-timer/state.json`             |
| Tarefas                | `~/.config/tomato-timer/tasks.json`             |
| Notas                  | `~/Documentos/Tomato Notes/*.md`                |
| Estado para a barra    | `$XDG_RUNTIME_DIR/tomato-timer/panel.json`      |

## Estrutura

```
tomato_timer.py          janela principal, timer, sons e opções
tomato_tasks.py          aba Tasks
tomato_notes.py          aba Notes
panel-extension/         extensão do GNOME Shell (barra superior)
install.sh/uninstall.sh  instalação local em ~/.local
```
