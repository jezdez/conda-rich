"""
Defines a "rich" reporter backend
This reporter handler provides the default output for conda.
"""

from __future__ import annotations

from contextlib import contextmanager
from os.path import basename, dirname
from typing import TYPE_CHECKING

from rich.console import Console
from rich.progress import Progress

from conda.base.constants import ROOT_ENV_NAME
from conda.base.context import context
from conda.common.path import paths_equal
from conda.exceptions import CondaError
from conda.plugins import CondaReporterBackend, hookimpl
from conda.plugins.types import ProgressBarBase, ReporterRendererBase

if TYPE_CHECKING:
    from typing import ContextManager
    from collections.abc import Callable


class QuietProgressBar(ProgressBarBase):
    """
    Progress bar class used when no output should be printed
    """

    def __init__(self, description, io_context_manager, **kwargs):
        super().__init__(description, io_context_manager, **kwargs)

        with self._io_context_manager as file:
            file.write(f"...downloading {description}...\n")

    def update_to(self, fraction) -> None:
        pass

    def refresh(self) -> None:
        pass

    def close(self) -> None:
        pass


class RichProgressBar(ProgressBarBase):
    def __init__(
        self,
        description: str,
        io_context_manager: Callable[[], ContextManager],
        progress_context_managers=None,
        **kwargs,
    ) -> None:
        super().__init__(description, io_context_manager)

        self.progress: Progress | None = None

        # We are passed in a list of context managers. Only one of them
        # is allowed to be the ``rich.Progress`` one we've defined. We
        # find it and then set it to ``self.progress``.
        for progress in progress_context_managers:
            if isinstance(progress, Progress):
                self.progress = progress
                break

        # Unrecoverable state has been reached
        if self.progress is None:
            raise CondaError(
                "Rich is configured, but there is no progress bar available"
            )

        self.task = self.progress.add_task(description, total=1)

    def update_to(self, fraction) -> None:
        if self.progress is not None:
            self.progress.update(self.task, completed=fraction)

            if fraction == 1:
                self.progress.update(self.task, visible=False)

    def close(self) -> None:
        if self.progress is not None:
            self.progress.stop_task(self.task)

    def refresh(self) -> None:
        if self.progress is not None:
            self.progress.refresh()


class RichReporterRenderer(ReporterRendererBase):
    """
    Default implementation for console reporting in conda
    """

    def detail_view(self, data: dict[str, str | int | bool], **kwargs) -> str:
        table_parts = [""]
        longest_header = max(map(len, data.keys()))

        for header, value in data.items():
            table_parts.append(f" {header:>{longest_header}} : {value}")

        table_parts.append("\n")

        return "\n".join(table_parts)

    def envs_list(self, data, **kwargs) -> str:
        output = ["", "# conda environments:", "#"]

        def disp_env(prefix):
            active = "*" if prefix == context.active_prefix else " "
            if prefix == context.root_prefix:
                name = ROOT_ENV_NAME
            elif any(
                paths_equal(envs_dir, dirname(prefix)) for envs_dir in context.envs_dirs
            ):
                name = basename(prefix)
            else:
                name = ""
            return f"{name:20} {active} {prefix}"

        for env_prefix in data:
            output.append(disp_env(env_prefix))

        output.append("\n")

        return "\n".join(output)

    def progress_bar(
        self,
        description: str,
        io_context_manager: Callable[[], ContextManager],
        **kwargs,
    ) -> ProgressBarBase:
        """
        Determines whether to return a RichProgressBar or QuietProgressBar
        """
        if context.quiet:
            return QuietProgressBar(description, io_context_manager, **kwargs)
        else:
            return RichProgressBar(description, io_context_manager, **kwargs)

    @classmethod
    def progress_bar_context_manager(cls, io_context_manager) -> ContextManager:
        @contextmanager
        def rich_context_manager():
            with io_context_manager as file:
                console = Console(file=file)
                with Progress(transient=True, console=console) as progress:
                    yield progress

        return rich_context_manager()


@hookimpl
def conda_reporter_backends():
    """
    Reporter backend for rich
    """
    yield CondaReporterBackend(
        name="rich",
        description="Rich implementation for console reporting in conda",
        renderer=RichReporterRenderer,
    )
