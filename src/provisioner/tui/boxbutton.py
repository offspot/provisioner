import typing

import urwid as uw

if typing.TYPE_CHECKING:
    from urwid.widget.popup import PopUpParametersModel
else:

    class PopUpParametersModel(dict): ...


class BoxButton(uw.WidgetWrap):

    def __init__(
        self,
        label,
        on_press=None,
        label_palette_id: str = "btn",
        lines_palette_id: str = "btn_lines",
    ):
        label_widget = uw.Text(label, align="center")
        label_widget = uw.AttrMap(
            label_widget, label_palette_id, f"{label_palette_id}_focus"
        )
        self.widget = uw.AttrMap(
            uw.LineBox(label_widget), lines_palette_id, f"{lines_palette_id}_focus"
        )
        self.hidden_button = uw.Button("hidden button", on_press=on_press)
        super().__init__(self.widget)

    def selectable(self):
        return True

    def keypress(self, *args, **kwargs):
        return self.hidden_button.keypress(*args, **kwargs)

    def mouse_event(self, *args, **kwargs):
        return self.hidden_button.mouse_event(*args, **kwargs)


class ConfirmPopupDialog(uw.WidgetWrap):

    signals: typing.ClassVar[list[str]] = ["close"]

    def __init__(
        self,
        on_press,
        question_text: str = "Are you sure?",
        confirm_label: str = "Yes",
        cancel_label: str = "Cancel",
    ):
        cancel_button = BoxButton(
            cancel_label,
            label_palette_id="popup_cancel_btn",
            lines_palette_id="popup_cancel_btn_lines",
        )
        confirm_button = BoxButton(
            confirm_label,
            on_press=on_press,
            label_palette_id="popup_confirm_btn",
            lines_palette_id="popup_confirm_btn_lines",
        )
        uw.connect_signal(
            cancel_button.hidden_button, "click", lambda btn: self._emit("close")
        )
        question = uw.AttrMap(uw.Text(question_text), "popup_question")
        pile = uw.Pile(
            [
                uw.Divider(top=0, bottom=0),
                question,
                uw.Divider(top=0, bottom=0),
                uw.Columns([cancel_button, confirm_button]),
            ]
        )
        super().__init__(
            uw.AttrMap(
                uw.Filler(uw.Padding(pile, left=1, right=1), valign=uw.TOP), "popup"
            )
        )

    def keypress(self, size: tuple[int], key: str) -> str | None:
        if key == "esc":
            self._emit("close")
        return super().keypress(size=size, key=key)


class ConfirmingBoxButton(uw.PopUpLauncher):
    def __init__(
        self,
        label: str,
        on_press,
        question: str = "Are you sure?",
        confirm_label: str = "Yes",
        cancel_label: str = "Cancel",
    ) -> None:
        super().__init__(
            BoxButton(label=f"{label} [❓]", label_palette_id="confirm_btn")
        )
        self.question_text = question
        self.confirm_label = confirm_label
        self.cancel_label = cancel_label
        self.on_confirm = on_press
        uw.connect_signal(
            self.original_widget.hidden_button, "click", lambda btn: self.open_pop_up()
        )

    def create_pop_up(self) -> ConfirmPopupDialog:
        pop_up = ConfirmPopupDialog(
            on_press=self.on_confirm,
            question_text=self.question_text,
            confirm_label=self.confirm_label,
            cancel_label=self.cancel_label,
        )
        uw.connect_signal(pop_up, "close", lambda btn: self.close_pop_up())
        return pop_up

    def get_pop_up_parameters(self) -> PopUpParametersModel:
        return {"left": 0, "top": 1, "overlay_width": 40, "overlay_height": 10}


class InfoPopupDialog(uw.WidgetWrap):

    signals: typing.ClassVar[list[str]] = ["close"]

    def __init__(
        self,
        message: str = "n/a",
        btn_label: str = "Ok",
    ):
        button = BoxButton(
            btn_label,
            label_palette_id="popup_confirm_btn",
            lines_palette_id="popup_confirm_btn_lines",
        )
        uw.connect_signal(button.hidden_button, "click", lambda _: self._emit("close"))
        question = uw.AttrMap(uw.Text(message), "popup_question")
        pile = uw.Pile(
            [
                uw.Divider(top=0, bottom=0),
                question,
                uw.Divider(top=0, bottom=0),
                uw.Columns([button]),
            ]
        )
        super().__init__(
            uw.AttrMap(
                uw.Filler(uw.Padding(pile, left=1, right=1), valign=uw.TOP), "popup"
            )
        )

    def keypress(self, size: tuple[int], key: str) -> str | None:
        if key == "esc":
            self._emit("close")
        return super().keypress(size=size, key=key)


class InfoPopupBoxButton(uw.PopUpLauncher):
    def __init__(
        self,
        label: str,
        message: str = "n/a",
        btn_label: str = "Ok",
    ) -> None:
        super().__init__(BoxButton(label=f"{label}", label_palette_id="confirm_btn"))
        self.message = message
        self.btn_label = btn_label
        uw.connect_signal(
            self.original_widget.hidden_button, "click", lambda _: self.open_pop_up()
        )

    def create_pop_up(self) -> ConfirmPopupDialog:
        pop_up = InfoPopupDialog(
            message=self.message,
            btn_label=self.btn_label,
        )
        uw.connect_signal(pop_up, "close", lambda _: self.close_pop_up())
        return pop_up

    def get_pop_up_parameters(self) -> PopUpParametersModel:
        return {"left": 0, "top": 1, "overlay_width": 40, "overlay_height": 10}
