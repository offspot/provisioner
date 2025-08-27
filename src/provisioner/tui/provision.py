import datetime
import functools
import time
from threading import Thread

import urwid as uw

from provisioner.constants import FAILURE_SOUNDS, RC_HALT, RC_REBOOT, SUCCESS_SOUNDS
from provisioner.context import Context
from provisioner.provisioning.common import Environment, ImagerStats, Step
from provisioner.provisioning.manager import ProvisionManager
from provisioner.provisioning.resizepart import ResizePartitionStep
from provisioner.tui.boxbutton import BoxButton
from provisioner.tui.pane import Pane
from provisioner.tui.spinner import SpinnerText
from provisioner.utils.imgprobe import ImageFileInfo
from provisioner.utils.misc import (
    format_dt,
    format_duration,
    format_size,
    format_speed,
    get_estimated_duration,
    get_now,
    padding,
    playsounds,
)

context = Context.get()
one_minute = 60


class ProvisionPane(Pane):

    def render(self):
        self.loading_text = SpinnerText("Gathering information…", align="center")
        self.uloop.widget = uw.AttrMap(uw.SolidFill(), "bg_prov")
        self.main_widget = uw.Filler(uw.Pile([], focus_item=1), valign="top")

        if (get_now() - self.host.queried_on).total_seconds() > one_minute:
            return self.render_without_host()
        self.render_with_host()

    def render_without_host(self):
        pile: uw.Pile = (
            self.main_widget.base_widget
        )  # pyright: ignore reportAssignmentType

        # paint a text line surrounded by two lines of decor
        div = uw.Divider()
        outside = uw.AttrMap(div, "outside")
        inside = uw.AttrMap(div, "inside")
        streak = uw.AttrMap(
            self.loading_text,
            "streak",
        )
        widgets: list[uw.Widget] = [
            outside,
            inside,
            streak,
            inside,
            outside,
            uw.Divider(),
        ]

        for widget in widgets:
            pile.contents.append(
                (widget, self.std_option)  # pyright: ignore reportArgumentType
            )

        # request spinner text to animate
        self.loading_text.animate(self.uloop)

        self.update()

        # start thread gathering infos from host
        Thread(target=self.gather_infos).start()

    def gather_infos(self):
        self.host.query_all()
        self.loading_text.done("")
        pile = self.pile
        pile.contents.clear()
        self.update()
        self.render_with_host()

    def render_with_host(self):
        self.target_disk = self.host.dev.nvme_target_disk

        pile: uw.Pile = (
            self.main_widget.base_widget
        )  # pyright: ignore reportAssignmentType

        # paint a text line surrounded by two lines of decor
        div = uw.Divider()
        outside = uw.AttrMap(div, "outside")
        inside = uw.AttrMap(div, "inside")
        streak = uw.AttrMap(
            uw.Text(
                f"{self.host.model}"
                f" – S/N: {self.host.serial_number.upper()}",  # noqa: RUF001
                align=uw.Align.CENTER,
            ),
            "streak",
        )
        widgets: list[uw.Widget] = [
            outside,
            inside,
            streak,
            inside,
            outside,
            uw.Divider(),
        ]
        for widget in widgets:
            pile.contents.append(
                (widget, self.std_option)  # pyright: ignore reportArgumentType
            )

        self.menu: uw.Pile = uw.Pile(widget_list=[])
        self.menu_in_pile = False

        self.render_image_chooser()

    def render_image_chooser(self):
        pile: uw.Pile = (
            self.main_widget.base_widget
        )  # pyright: ignore reportAssignmentType
        if self.menu_in_pile:
            self.menu.contents.clear()
            pile.contents.pop()

        if self.host.dev.has_single_image:
            return self.on_image_selected(self.host.dev.images[0])

        filtered_images: list[ImageFileInfo] = list(
            filter(lambda img: img.size > self.target_disk.size, self.host.dev.images)
        )

        # display image selector
        title_text = "Select source Image"
        if filtered_images:
            title_text += f" ({len(filtered_images)} excluded as too large for disk)"
        self.append_to(
            self.menu,
            uw.AttrMap(
                uw.Text(title_text, align=uw.Align.CENTER),
                "highlight_prov",
            ),
        )
        self.append_to(self.menu, self.a_divider)

        for image in self.host.dev.images:
            if image in filtered_images:
                continue

            self.append_to(
                self.menu,
                uw.Button(
                    f"{padding(format_size(image.size), 10)} "
                    f"{image.name} ({image.fpath.name})",
                    on_press=functools.partial(self.on_image_selected, image),
                ),
            )
        if hasattr(self, "image"):
            self.menu.focus_position = self.host.dev.images.index(self.image) + 1
        else:
            self.menu.focus_position = 2  # first is intro text

        self.append_to(self.menu, uw.Button("Cancel", on_press=self.go_home))

        decorated_menu = uw.Padding(
            self.menu,
            align=uw.Align.CENTER,
            width=(uw.WHSettings.RELATIVE, 50),
            min_width=50,
        )
        self.append_to(pile, decorated_menu)
        self.menu_in_pile = True
        pile.focus_position = len(pile.contents) - 1

        self.update()

    def on_image_selected(self, image: ImageFileInfo, *args):  # noqa: ARG002
        self.image = image

        self.menu.contents.clear()
        self.header_text = uw.Text("Confirm provisioning", align=uw.Align.CENTER)
        self.append_to(
            self.menu,
            uw.AttrMap(
                self.header_text,
                "highlight_prov",
            ),
        )
        self.append_to(self.menu, self.a_divider)
        self.append_to(
            self.menu,
            uw.Text(
                f"{padding('Device', 10, on_end=True)}: {self.host.model}"
                f" – S/N: {self.host.serial_number.upper()}",  # noqa: RUF001
                align=uw.Align.LEFT,
            ),
        )
        self.append_to(
            self.menu,
            uw.Text(
                f"{padding('Image', 10, on_end=True)}: "
                f"{format_size(self.image.size)} {self.image.name}",
                align=uw.Align.LEFT,
            ),
        )
        self.append_to(
            self.menu,
            uw.Text(
                f"{padding('Disk', 10, on_end=True)}: {self.target_disk!s}",
                align=uw.Align.LEFT,
            ),
        )
        self.append_to(
            self.menu,
            uw.Text(
                f"{padding('Profile', 10, on_end=True)}: Kiwix Hotspot H1",
                align=uw.Align.LEFT,
            ),
        )
        self.exptected_duration = get_estimated_duration(self.image.size)
        self.append_to(
            self.menu,
            uw.Text(
                f"{padding('Duration', 10, on_end=True)}: "
                f"{format_duration(self.exptected_duration)} "
                "(est.)",
                align=uw.Align.LEFT,
            ),
        )
        self.append_to(self.menu, self.a_divider)
        self.append_to(
            self.menu,
            uw.AttrMap(
                uw.Text(
                    "Ready to start ?",
                    align=uw.Align.CENTER,
                ),
                "highlight_prov",
            ),
        )
        self.append_to(self.menu, self.a_divider)
        self.append_to(
            self.menu,
            uw.Columns(
                [
                    BoxButton("Cancel", on_press=self.on_cancel),
                    uw.Divider(),
                    BoxButton("Let's Go!", on_press=self.on_confirm),
                ]
            ),
        )
        self.menu.focus_position = len(self.menu.contents) - 1
        self.update()

    def on_cancel(self, *args):  # noqa: ARG002
        # self.app.switch_to("loading")
        self.render_image_chooser()

    def on_confirm(self, *args):  # noqa: ARG002
        self.header_text.set_text("Provisioning")
        # remove menu, divider and title text
        self.menu.contents.pop()
        self.menu.contents.pop()
        self.menu.contents.pop()

        self.started_on = datetime.datetime.now(tz=datetime.UTC)
        self.eta_on = self.started_on + datetime.timedelta(
            seconds=self.exptected_duration
        )

        self.append_to(
            self.menu,
            uw.Text(
                f"{padding('Started on', 10, on_end=True)}: "
                f"{format_dt(self.started_on)}"
            ),
        )
        self.append_to(
            self.menu,
            uw.Text(f"{padding('ETA', 10, on_end=True)}: {format_dt(self.eta_on)}"),
        )

        self.ended_on_text = uw.Text("")
        self.append_to(self.menu, self.ended_on_text)
        self.append_to(self.menu, self.a_divider)

        self.spinner = SpinnerText("Preparing…", style="prov spinner")
        self.append_to(self.menu, self.spinner)

        self.progressbar = uw.ProgressBar(
            "pg normal", "pg complete", 0, 100, "pg smooth"
        )
        self.progressbar.set_completion(0)

        Thread(target=self.do_provision).start()

        self.update()

    def do_provision(self):
        environment = Environment(
            host=self.host,
            image=self.image,
            image_device=self.host.dev.get_disk_from_name(self.image.device),
            target_disk=self.target_disk,
        )

        if not environment.image_fits_target:
            return self.on_error(
                f"Image {environment.image.name} "
                f"({format_size(environment.image.size)}) "
                f"does not fit target {environment.target_disk}"
            )

        manager = ProvisionManager(
            environment=environment, progressbar=self.progressbar
        )

        def update_pg(pg: uw.ProgressBar, step: Step):
            while step.running:
                pg.set_completion(step.progress)
                progress_text = getattr(step, "progress_text", "")
                if progress_text:
                    self.spinner.set_message(
                        f"{step.prefix} {step.name}: {progress_text}"
                    )
                time.sleep(step.progress_interval_ms / 1000)

        failed = False
        advice = ""
        self.current_step = None
        self.imager_stats = ImagerStats(started_on=get_now(), ended_on=get_now())
        with manager as runner:
            for self.current_step in runner:
                step = self.current_step
                try:
                    self.spinner.set_message(f"{step.prefix} {step.name}")
                    self.spinner.animate(self.uloop)
                    step.running = True
                    if step.reports_progress:
                        self.progressbar.set_completion(0)
                        self.append_to(self.menu, self.progressbar)
                        Thread(
                            target=update_pg,
                            kwargs={"pg": self.progressbar, "step": step},
                        ).start()
                    res = step.run(verbose=False)
                    step.running = False
                    self.ended_on = get_now()
                    if step.ident == "imager" and res.imager_stats:
                        self.imager_stats = res.imager_stats
                    if res.succeeded:
                        self.spinner.done(
                            f"{step.prefix} {step.name} {res.success_text}"
                        )
                        if step.reports_progress:
                            # remove progressbar
                            self.menu.contents.pop()
                    else:
                        failed = True
                        self.spinner.done(
                            f"{step.prefix} {step.name}\n↳ Error: {res.error_text}"
                        )
                        advice = res.advice
                        break
                except Exception as exc:
                    failed = True
                    advice = f"Error: {exc!s}"
                    self.spinner.done(
                        f"{step.prefix} {step.name}: Unexpected exception"
                    )
                    self.ended_on = get_now()
                    break
            self.current_step = None
        self.ended_on_text.set_text(
            f"{padding('Ended on', 10, on_end=True)}: {format_dt(self.ended_on)}"
        )
        if not failed:
            return self.on_success("Provisioning completed successfuly 🎉")

        return self.on_error(
            "Provisioning failed.", advice=f"\n{advice}" if advice else "", step=step
        )

    def stop(self):
        step = getattr(self, "current_step", None)
        if step:
            try:
                step.kill()
            except Exception:
                ...

    def on_error(
        self, message: str = "Error", advice: str = "", step: Step | None = None
    ):
        self.append_to(self.menu, self.a_divider)
        content = f"\n{message}\n"
        if advice:
            content += f"ℹ️  {advice}\n"  # noqa: RUF001
        if step and ProvisionManager.STEPS.index(
            type(step)
        ) >= ProvisionManager.STEPS.index(ResizePartitionStep):
            content += "You are adviced to reboot before trying again.\n"
        self.append_to(
            self.menu, uw.AttrMap(uw.Text(content, align=uw.Align.CENTER), "prov error")
        )

        self.append_to(self.menu, self.a_divider)
        self.append_to(
            self.menu,
            uw.Columns(
                [
                    BoxButton(label="Cancel", on_press=self.go_home),
                    uw.Divider(),
                    BoxButton(label="Reboot", on_press=self.reboot),
                ]
            ),
        )
        self.update()
        self.menu.focus_position = len(self.menu.contents) - 1
        self.update()
        self.print_stats()
        self.audio_feedback(FAILURE_SOUNDS)

    def on_success(self, message: str = "Success"):
        # remove the spinner
        self.menu.contents.pop()

        self.append_to(self.menu, self.a_divider)
        content = f"\n{message}\n"
        content += (
            "You can now shut the device down, remove all external devices\n"
            "and start testing.\n"
        )
        self.append_to(
            self.menu,
            uw.AttrMap(
                uw.Text(content, align=uw.Align.CENTER),
                "prov success",
            ),
        )

        self.append_to(self.menu, self.a_divider)
        self.append_to(
            self.menu,
            uw.Columns(
                [
                    uw.Divider(),
                    BoxButton(label="Shutdown", on_press=self.shutdown),
                    uw.Divider(),
                ]
            ),
        )
        self.update()
        self.menu.focus_position = len(self.menu.contents) - 1
        self.print_stats()
        self.audio_feedback(SUCCESS_SOUNDS)

    def print_stats(self):
        if not self.imager_stats or not self.imager_stats.write_duration:
            return

        self.append_to(self.menu, self.a_divider)
        self.append_to(
            self.menu,
            uw.AttrMap(
                uw.Text(f"Imaging stats (flashing {format_size(self.image.size)})"),
                "highlight_prov",
            ),
        )

        writing_line = f"{format_duration(self.imager_stats.write_duration)}"
        if self.imager_stats.write_done:
            writing_line += (
                f" ({format_speed(self.image.size, self.imager_stats.write_duration)})"
            )
        else:
            writing_line += " (incomplete)"
        lines = {"Writing duration": writing_line}

        if self.imager_stats.verify_duration:
            verify_line = f"{format_duration(self.imager_stats.verify_duration)}"
            if self.imager_stats.verify_done:
                verify_speed = format_speed(
                    self.image.size, self.imager_stats.verify_duration
                )
                verify_line += f" ({verify_speed})"
            else:
                verify_line += " (incomplete)"
            lines.update({"Verify duration": verify_line})

        if self.imager_stats.verify_done:
            overall_line = f"{format_duration(self.imager_stats.duration)}"
            overall_speed = format_speed(self.image.size, self.imager_stats.duration)
            overall_line += f" ({overall_speed})"
            lines.update({"Overall duration": overall_line})

        name_len = max(len(name) for name in lines.keys())
        for name, value in lines.items():
            self.append_to(
                self.menu,
                uw.Text(f"{padding(text=name, size=name_len, on_end=True)}: {value}"),
            )

    def audio_feedback(self, fnames: list[str]):
        fpaths = list(
            filter(
                lambda f: f.exists(),
                [context.audio_dir.joinpath(fname) for fname in fnames],
            )
        )
        playsounds(fpaths)

    def reboot(self, *args):  # noqa: ARG002
        self.app.stop(exit_code=RC_REBOOT)

    def shutdown(self, *args):  # noqa: ARG002
        self.app.stop(exit_code=RC_HALT)

    def go_home(self, *args):  # noqa: ARG002
        self.app.switch_to("loading")
