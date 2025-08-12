import urwid as uw


class SpinnerText(uw.Text):
    _steps = ("⠄", "⠆", "⠇", "⠋", "⠙", "⠸", "⠰", "⠠")
    _interval_ms = 80

    def __init__(self, message: str, *args, **kwargs):
        self.loop = None
        self.is_loading = True
        self._index = -1
        self._message = message
        super().__init__(self.get_next(), *args, **kwargs)

    def done(self, message: str):
        self.is_loading = False
        self.set_text(message)

    @property
    def _interval(self) -> float:
        return 1 / 1000 * self._interval_ms

    def get_next(self) -> tuple[str, str]:
        if self._index >= len(self._steps) - 1:
            self._index = 0
        else:
            self._index += 1
        return ("streak", f"{self._steps[self._index]} {self._message}")

    def next_frame(self):
        self.set_text(self.get_next())

    def set_message(self, message: str):
        self._message = message

    def animate(self, loop: uw.MainLoop):
        self.loop = loop
        self.is_loading = True

        async def animator():
            def update(*args):
                if self.is_loading:
                    self.next_frame()
                    self.loop.set_alarm_in(self._interval, update)

            update()

        self.loop.event_loop._loop.create_task(animator())
