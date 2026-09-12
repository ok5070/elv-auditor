import os
import shutil
import subprocess
import tempfile
from pathlib import Path

class CADConverter:
    ODA_PATH = "/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter"

    @classmethod
    def get_binary_path(cls) -> str:
        if os.path.exists(cls.ODA_PATH):
            return cls.ODA_PATH
        system_bin = shutil.which("ODAFileConverter")
        if system_bin:
            return system_bin
        raise FileNotFoundError("ODAFileConverter не найден в системе (/Applications или PATH)")

    @classmethod
    def convert_dwg_to_dxf(cls, dwg_bytes: bytes, filename: str) -> bytes:
        oda_bin = cls.get_binary_path()
        stem = Path(filename).stem or "drawing"

        with tempfile.TemporaryDirectory() as tmpdir:
            in_dir = os.path.join(tmpdir, "in")
            out_dir = os.path.join(tmpdir, "out")
            os.makedirs(in_dir, exist_ok=True)
            os.makedirs(out_dir, exist_ok=True)

            input_dwg_path = os.path.join(in_dir, f"{stem}.dwg")
            with open(input_dwg_path, "wb") as f:
                f.write(dwg_bytes)

            cmd = [
                oda_bin,
                in_dir,
                out_dir,
                "ACAD2018",
                "DXF",
                "0",
                "1",
                "*.DWG"
            ]

            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
            except subprocess.TimeoutExpired:
                raise RuntimeError("Конвертация DWG в DXF прервана по таймауту (45 сек)")

            if res.returncode != 0:
                raise RuntimeError(f"Ошибка ODA Converter (код {res.returncode}): {res.stderr or res.stdout}")

            output_files = list(Path(out_dir).glob("*.dxf")) + list(Path(out_dir).glob("*.DXF"))
            if not output_files:
                raise FileNotFoundError(f"Файл DXF не был создан ODA Converter. Вывод: {res.stdout}")

            with open(output_files[0], "rb") as f:
                return f.read()
