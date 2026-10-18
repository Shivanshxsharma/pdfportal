"""What every tool receives."""

from dataclasses import dataclass, field

from .protocol import Reporter


@dataclass
class Job:
    inputs: list                       # absolute paths, in the order they were dropped
    options: dict = field(default_factory=dict)
    fallback_dir: str = ""             # where results go if the input's folder is read-only
    reporter: Reporter = field(default_factory=Reporter)

    def option(self, name, default=None):
        value = self.options.get(name)
        return default if value is None or value == "" else value

    @property
    def input_password(self) -> str:
        """Opens locked inputs. The app asks for it after a "needs_password"
        error and runs the job again with it set."""
        return str(self.options.get("input_password") or "")
