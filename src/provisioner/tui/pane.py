import urwid as uw

from provisioner.tui.app import App


class Pane:
    def __init__(self, app: App) -> None:
        self.app = app
        self.main_widget: uw.Widget = self.app.placeholder
        self.render()
        self.uloop.widget.original_widget = self.main_widget

    @property
    def host(self):
        return self.app.host

    @property
    def uloop(self):
        return self.app.uloop

    def update(self):
        self.app.update()

    def render(self):
        raise NotImplementedError("!")

    def destroy(self): ...


class ExitPane(Pane):
    def render(self):
        self.main_widget = self.app.placeholder
