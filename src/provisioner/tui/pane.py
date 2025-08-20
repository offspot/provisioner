from typing import Literal, TypeAlias

import urwid as uw

from provisioner.tui.app import App

PileOptions: TypeAlias = (
    tuple[Literal[uw.WHSettings.PACK], None]
    | tuple[Literal[uw.WHSettings.GIVEN], int]
    | tuple[Literal[uw.WHSettings.WEIGHT], int | float]
)
WidgetListEntry: TypeAlias = tuple[uw.Widget, PileOptions]


class Pane:
    def __init__(self, app: App) -> None:
        self.app = app
        self.main_widget: uw.Widget = self.app.placeholder
        self.render()

        self.uloop.widget.original_widget = (  # type: ignore reportAttributeAccessIssue
            self.main_widget
        )

    @property
    def host(self):
        return self.app.host

    @property
    def uloop(self):
        return self.app.uloop

    @property
    def pile(self) -> uw.Pile:
        pile: uw.Pile = (
            self.main_widget.base_widget  # .base_widget skips the decorations
        )  # pyright: ignore reportAssignmentType
        return pile

    @property
    def a_divider(self) -> uw.Divider:
        return uw.Divider(top=0, bottom=0)

    @property
    def std_option(
        self,
    ) -> PileOptions:
        return (uw.WHSettings.WEIGHT, 10)

    def append_to(
        self,
        list_w: uw.Widget,
        widget: uw.Widget,
        options: PileOptions | None = None,
    ) -> WidgetListEntry:
        if options is None:
            options = self.std_option
        entry = (widget, options)
        list_w.contents.append(entry)  # pyright: ignore reportAttributeAccessIssue
        return entry

    def remove_from(self, list_w: uw.Widget, entry: WidgetListEntry | uw.Widget):
        list_w.contents.remove(entry)  # pyright: ignore reportAttributeAccessIssue

    def stop(self): ...

    def update(self):
        self.app.update()

    def render(self):
        raise NotImplementedError("!")

    def destroy(self): ...


class ExitPane(Pane):
    def render(self):
        self.main_widget = self.app.placeholder
