"""Build a private Linux/Python 3.12 Lambda archive locally; never deploy."""
import argparse
import ast
import json
import subprocess
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--uv', default='uv')
    args = parser.parse_args()
    tree = ast.parse((ROOT/'scripts/package_web.py').read_text(encoding='utf-8'))
    allow = next(ast.literal_eval(node.value) for node in tree.body
                 if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id=='allow' for t in node.targets))
    allow += ['backend/lambda_entry.py', 'backend/runtime_config.py']
    allow += ['data/sources/'+s['name'] for s in json.loads((ROOT/'data/manifest.json').read_text(encoding='utf-8'))]
    allow = sorted(set(allow))
    output = ROOT/'artifacts/growthai-lambda.zip'
    output.parent.mkdir(exist_ok=True)
    # Isolated build directory; cleanup never touches the project or other temp files.
    with tempfile.TemporaryDirectory(prefix='growthai-lambda-') as folder:
        build = Path(folder).resolve()
        assert build.parent == Path(tempfile.gettempdir()).resolve()
        requirements = build/'locked.txt'
        subprocess.run([args.uv, 'export', '--frozen', '--no-dev', '--no-hashes',
                        '--format', 'requirements-txt', '--output-file', str(requirements)],
                       cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
        deps = build/'packages'
        subprocess.run([args.uv, 'pip', 'install', '--requirements', str(requirements),
                        '--python-version', '3.12', '--python-platform', 'x86_64-manylinux_2_28',
                        '--only-binary', ':all:', '--target', str(deps)], check=True)
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            for relative in allow:
                if relative.startswith('.') or relative in ('Dockerfile', 'render.yaml', 'vercel.json', 'pyproject.toml', 'uv.lock', 'requirements.txt'):
                    continue
                path = (ROOT/relative).resolve()
                assert path.is_relative_to(ROOT.resolve()) and path.is_file()
                archive.write(path, relative)
            for path in deps.rglob('*'):
                if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                    archive.write(path, path.relative_to(deps).as_posix())
        with zipfile.ZipFile(output) as archive:
            total = sum(i.file_size for i in archive.infolist())
            assert total < 250*1024*1024, 'Lambda extracted size limit exceeded'
            assert not any(n.startswith(('.env', '.aws/', '.vercel/')) for n in archive.namelist())
            assert 'backend/lambda_entry.py' in archive.namelist()
        print(json.dumps(dict(archive=str(output), zipped_bytes=output.stat().st_size,
                              extracted_bytes=total, uploaded=False)))


if __name__ == '__main__':
    main()
