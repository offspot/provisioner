from typing import Literal, TypeAlias

import urwid as uw

from provisioner.host import ProvisionHost
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
    def host(self) -> ProvisionHost:
        return self.app.host

    @property
    def uloop(self) -> uw.MainLoop:
        """the urwid loop of the app"""
        return self.app.uloop

    @property
    def pile(self) -> uw.Pile:
        """the base_widget of the pane casted as Pile (might be wrong)"""
        pile: uw.Pile = (
            self.main_widget.base_widget  # .base_widget skips the decorations
        )  # pyright: ignore reportAssignmentType
        return pile

    @property
    def a_divider(self) -> uw.Divider:
        """a blank Divider instance"""
        return uw.Divider(top=0, bottom=0)

    @property
    def std_option(
        self,
    ) -> PileOptions:
        """our default options for in-list items"""
        return (uw.WHSettings.WEIGHT, 10)

    def append_to(
        self,
        list_w: uw.Widget,
        widget: uw.Widget,
        options: PileOptions | None = None,
    ) -> WidgetListEntry:
        """append a widget to a list widget (shortcut due to typing issue)"""
        if options is None:
            options = self.std_option
        entry = (widget, options)
        list_w.contents.append(entry)  # pyright: ignore reportAttributeAccessIssue
        return entry

    def remove_from(self, list_w: uw.Widget, entry: WidgetListEntry | uw.Widget):
        """remove a widget from a list widget (shortcut due to typing issue)"""
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
