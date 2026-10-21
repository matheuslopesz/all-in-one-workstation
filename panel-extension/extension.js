import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const APP_ID = 'dev.matheus.AllInOneWorkstation';
const COLORS = {pomodoro: '#ff5555', short: '#8be9fd', long: '#bd93f9'};

export default class WorkstationPanel extends Extension {
    enable() {
        this._path = GLib.build_filenamev([GLib.get_user_runtime_dir(), 'all-in-one-workstation', 'panel.json']);
        this._button = new PanelMenu.Button(0.0, 'All-in-One Workstation', true);
        this._icon = new St.Icon({icon_name: 'alarm-symbolic', style_class: 'system-status-icon'});
        this._label = new St.Label({y_align: Clutter.ActorAlign.CENTER});
        const box = new St.BoxLayout();
        box.add_child(this._icon);
        box.add_child(this._label);
        this._button.add_child(box);
        this._button.connect('button-press-event', () => {
            Gio.DesktopAppInfo.new(`${APP_ID}.desktop`)?.launch([], null);
            return Clutter.EVENT_STOP;
        });
        Main.panel.addToStatusArea(this.uuid, this._button, 0, 'center');
        this._tickId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 1, () => {
            this._update();
            return GLib.SOURCE_CONTINUE;
        });
        this._update();
    }

    disable() {
        GLib.source_remove(this._tickId);
        this._tickId = null;
        this._button.destroy();
        this._button = null;
        this._icon = null;
        this._label = null;
    }

    _readState() {
        try {
            const [, bytes] = GLib.file_get_contents(this._path);
            const state = JSON.parse(new TextDecoder().decode(bytes));
            return GLib.file_test(`/proc/${state.pid}`, GLib.FileTest.EXISTS) ? state : null;
        } catch {
            return null;
        }
    }

    _update() {
        const state = this._readState();
        if (!state) {
            this._button.hide();
            return;
        }
        const seconds = state.running
            ? Math.max(0, Math.ceil(state.end_at - Date.now() / 1000))
            : state.remaining;
        const clock = `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
        const style = `color: ${COLORS[state.mode] ?? 'white'}; font-weight: bold;`;
        this._label.text = `${clock}${state.running ? '' : ' ⏸'}`;
        this._label.style = style;
        this._icon.style = style;
        this._button.show();
    }
}
