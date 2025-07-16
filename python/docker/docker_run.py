from pathlib import Path
import shutil
import sys
import os


sys.path.append(str(Path(__file__).resolve().parent.parent.parent))  # add root sys.path

from python.file_util import read_env_file
from python.read_multi_util import multiple_selector
from python.msg_handler import error, string

# Set the default path
PARENT_DIR = Path(__file__).resolve().parent.parent.parent
CONF_DIR = (PARENT_DIR / "config/docker").resolve()

SECTION_INFRA = "infrastructure"
SECTION_APPS = "applications"


class DockerRun:

    def __init__(self):
        self.env_file = os.path.join(CONF_DIR, ".env")

    def _init_data(self, type):
        self.type = type
        self.env = read_env_file(self.env_file, type)
        if not self.env:
            error(f"No #={self.type}, Check {self.env_file}", ignore=True)
            sys.exit(1)  # no matched definition

    # ==============================================================================
    # (0) Function Tools
    # ==============================================================================
    def gene_env_section(self):
        """
        create lines before save data to .env file
        """
        lines = [f"#={self.type}\n"]
        for k, v in self.env.items():
            lines.append(f"{k}={v}\n")
        lines.append("\n")
        return lines

    def update_env(self, selected):
        """
        create lines before save data to .env file
        """
        for k in self.env.keys():
            if k in selected:
                self.env[k] = "True"
            else:
                self.env[k] = ""

    def save_env(self, backup=True):
        """
        retrieve network parameters, save to .env file
        """
        CONF_DIR.mkdir(parents=True, exist_ok=True)

        # if file does not exist, save the result to the file
        if not os.path.exists(self.env_file):
            lines = self.gene_env_section()
            with open(self.env_file, "w", encoding="utf-8") as f:
                f.writelines(lines)
            return

        # backup original config file
        backup_file = f"{self.env_file}.bak"
        if backup and not os.path.exists(backup_file):
            shutil.copy2(self.env_file, backup_file)

        # Read original file if it exists
        with open(self.env_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        new_lines = []
        i = 0
        add_target_block = False
        while i < len(lines):
            line = lines[i]
            i += 1
            if line.startswith(f"#={self.type}"):
                # replace the same section
                while i < len(lines):
                    if lines[i].startswith("#="):
                        break
                    i += 1  # skip lines
                new_lines.extend(self.gene_env_section())
                add_target_block = True

            elif line.startswith("#="):
                # add different sections
                new_lines.append(line)
                while i < len(lines):
                    if lines[i].startswith("#="):
                        break
                    else:
                        new_lines.append(lines[i])
                        i += 1

        if not add_target_block:
            lines.extend(self.gene_env_section())

        # write to config file
        with open(self.env_file, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

    def run_multiple_selector(self, type):
        """Choose the infrastructure | applications docker files"""
        self._init_data(type)
        options = []  # all available options
        default_selected = []  # default value
        for key, value in self.env.items():
            options.append(key)
            if value == "True":
                default_selected.append(key)

        selected = multiple_selector(options, default_selected, 3)
        self.update_env(selected)
        self.save_env()

    def run(self):
        string("\nPlease select the Docker infrastructure components to enable (multiple choices allowed): ")
        self.run_multiple_selector(SECTION_INFRA)
        string("\nnPlease select the Docker applications to enable (multiple choices allowed): ")
        self.run_multiple_selector(SECTION_APPS)


# Example usage:
if __name__ == "__main__":
    docker = DockerRun()
    docker.run()
    print(f"Docker version saved in: {docker.env_file}")
