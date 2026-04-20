from textual.app import App, ComposeResult
from textual.containers import Center, Vertical
from textual.widgets import Button, Footer, Header, Static


class ModeSelectApp(App):
    """Textual-based connection mode selector."""

    CSS = """
    Screen {
        align: center middle;
    }

    #card {
        width: 72;
        height: 20;
        border: round #4aa3ff;
        padding: 1 2;
        background: #111111;
    }

    #title {
        content-align: center middle;
        width: 100%;
        text-style: bold;
        color: #8fd3ff;
        margin-bottom: 1;
    }

    #hint {
        content-align: center middle;
        width: 100%;
        color: #aaaaaa;
        margin-top: 1;
    }

    Button {
        width: 100%;
        margin: 0 0 1 0;
    }
    """

    BINDINGS = [
        ("1", "select_lan", "LAN/WiFi"),
        ("2", "select_bluetooth", "Bluetooth"),
        ("3", "select_wan", "WAN/Internet"),
        ("q", "quit", "Quit"),
    ]

    selected_mode = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Center():
            with Vertical(id="card"):
                yield Static("Choose Connection Mode", id="title")
                yield Button("1) LAN/WiFi Connection", id="lan", variant="primary")
                yield Button("2) Bluetooth Connection", id="bluetooth")
                yield Button("3) WAN/Internet Connection", id="wan", variant="success")
                yield Button("Q) Quit", id="quit", variant="error")
                yield Static("Tip: You can use keys 1/2/3 or click buttons.", id="hint")
        yield Footer()

    def action_select_lan(self) -> None:
        self.selected_mode = "lan"
        self.exit()

    def action_select_bluetooth(self) -> None:
        self.selected_mode = "bluetooth"
        self.exit()

    def action_select_wan(self) -> None:
        self.selected_mode = "wan"
        self.exit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "lan":
            self.action_select_lan()
        elif button_id == "bluetooth":
            self.action_select_bluetooth()
        elif button_id == "wan":
            self.action_select_wan()
        elif button_id == "quit":
            self.selected_mode = None
            self.exit()


def select_connection_type_textual():
    app = ModeSelectApp()
    app.run()
    return app.selected_mode
