"""Set the campus download password without storing the password itself."""
import argparse
import base64
import getpass
import hashlib
import os
from pathlib import Path
import secrets
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', type=Path, default=Path(__file__).resolve().parents[1] / 'runtime/campus-site')
    parser.add_argument('--generate', action='store_true', help='Generate and display a new password once')
    args = parser.parse_args()
    password = secrets.token_urlsafe(15) if args.generate else getpass.getpass('Download password: ')
    if not 12 <= len(password) <= 256:
        parser.error('Use between 12 and 256 characters.')
    if not args.generate and password != getpass.getpass('Confirm password: '):
        parser.error('Passwords did not match.')
    if not args.site.is_dir():
        parser.error('The campus site directory does not exist.')
    salt = secrets.token_bytes(16)
    iterations = 600_000
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
    contents = f'iterations={iterations}\nsalt={base64.b64encode(salt).decode()}\nhash={base64.b64encode(digest).decode()}\n'
    target = args.site / 'download-password.properties'
    # Atomic replacement lets a running server pick up the new password immediately.
    with tempfile.NamedTemporaryFile(mode='w', encoding='ascii', dir=args.site, delete=False) as output:
        temporary = Path(output.name)
        output.write(contents)
    try:
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    print('Download password configured.')
    if args.generate:
        print(f'Password: {password}')


if __name__ == '__main__':
    main()
