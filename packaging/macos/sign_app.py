#!/usr/bin/env python3
"""Package a personal Helium fork with a stable Developer ID signature.

Use Chromium's list of code objects and entitlement assignments. Signing keys
remain in the macOS Keychain; this program accepts only their public identity.
"""

import argparse
import hashlib
import json
import plistlib
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace


def run(*command, capture=False):
    """Run a command without a shell or secret-bearing arguments."""
    result = subprocess.run([str(arg) for arg in command],
                            check=True,
                            capture_output=capture,
                            text=True)
    return result.stdout if capture else None


def configure_bundle(app, bundle_id, profile_dir, build_number=None, feed_url=None,
                     app_name='Helium Fork'):
    """Give the outer app and its helpers a consistent fork identity."""
    outer = app / 'Contents/Info.plist'
    original_id = plistlib.loads(outer.read_bytes())['CFBundleIdentifier']
    for path in app.rglob('Info.plist'):
        if path.is_symlink():
            continue
        info = plistlib.loads(path.read_bytes())
        identifier = info.get('CFBundleIdentifier', '')
        if identifier == original_id or identifier.startswith(original_id + '.'):
            info['CFBundleIdentifier'] = bundle_id + identifier[len(original_id):]
        if path == outer:
            info['CFBundleDisplayName'] = app_name
            info['CFBundleName'] = app_name
            info['CrProductDirName'] = profile_dir
            if build_number:
                info['CFBundleVersion'] = str(build_number)
                info['KSVersion'] = str(build_number)
            if feed_url:
                info['SUFeedURL'] = feed_url
                info['SUEnableAutomaticChecks'] = True
                info['SUAutomaticallyUpdate'] = True
                info['SUVerifyUpdateBeforeExtraction'] = True
                info['SURequireSignedFeed'] = True
        path.write_bytes(plistlib.dumps(info))


def signing_plan(source, source_app, app, bundle_id):
    """Read the code-object manifest from the matching patched Chromium tree."""
    sys.path.insert(0, str(source / 'chrome/installer/mac'))
    from signing import parts # pylint: disable=import-outside-toplevel,import-error
    from signing.model import CodeSignedProduct, CodeSignOptions

    framework = app / 'Contents/Frameworks/Helium Framework.framework'
    config = SimpleNamespace(app_product=app.stem,
                             product='Helium',
                             base_bundle_id=bundle_id,
                             framework_dir=str(framework),
                             codesign_requirements_outer_app='',
                             enable_updater=False,
                             use_static_angle=not (framework / 'Libraries/libEGL.dylib').exists(),
                             is_chrome_branded=lambda: False)
    objects = parts.get_parts(config)
    # The main app is the last object to sign. All nested code precedes its
    # containing framework, matching Chromium's signing.parts.sign_chrome().
    ordered = [(name, part) for name, part in objects.items()
               if name not in ('app', 'framework', 'privileged-helper')]
    sparkle = framework / 'Frameworks/Sparkle.framework'
    if sparkle.exists():
        # The matching platform build disables Sparkle's optional XPC services.
        # Refuse an unexpected layout rather than ship unsigned nested code.
        if list(sparkle.rglob('*.xpc')):
            raise ValueError('This packager expects Sparkle without XPC services')
        for name, identifier in (
                ('Autoupdate', 'org.sparkle-project.Sparkle.Autoupdate'),
                ('Updater.app', 'org.sparkle-project.Sparkle.Updater')):
            ordered.append(('sparkle-' + name, CodeSignedProduct(
                str(sparkle / 'Versions/Current' / name), identifier,
                options=CodeSignOptions.FULL_HARDENED_RUNTIME_OPTIONS)))
        ordered.append(('sparkle', CodeSignedProduct(str(sparkle), 'org.sparkle-project.Sparkle')))
    ordered += [('framework', objects['framework']), ('app', objects['app'])]
    plan = []
    for name, part in ordered:
        path = Path(part.path)
        if not path.is_absolute():
            path = app.parent / path
        if not path.exists():
            raise FileNotFoundError(f'Missing Chromium signing object: {path}')
        entitlements = None
        if part.entitlements:
            entitlements = source / 'chrome/app' / part.entitlements
            # The generated outer-app entitlements are the build's authority.
            if name == 'app':
                entitlements = source_app.parent / 'gen/chrome/app-entitlements.plist'
            if not entitlements.is_file():
                raise FileNotFoundError(entitlements)
            values = plistlib.loads(entitlements.read_bytes())
            if values.get('com.apple.security.get-task-allow'):
                raise ValueError('Release signing refuses get-task-allow')
            if any('${' in str(value) for value in values.values()):
                raise ValueError(f'Unexpanded entitlement in {entitlements}')
        plan.append((name, path, part, entitlements))
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chromium-src', type=Path, required=True)
    parser.add_argument('--source-app', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--identity', required=True, help='Certificate SHA-1 fingerprint')
    parser.add_argument('--team-id', required=True)
    parser.add_argument('--bundle-id', default='eu.cabraja.helium')
    parser.add_argument('--profile-dir', default='eu.cabraja.helium')
    parser.add_argument('--app-name', default='Helium Fork',
                        help='Display and bundle-directory name for an isolated review app')
    parser.add_argument('--build-number', type=int, help='Increasing Sparkle build version')
    parser.add_argument('--feed-url', help='HTTPS Sparkle appcast URL')
    parser.add_argument('--public-key', help='Expected public Sparkle Ed25519 key')
    parser.add_argument('--archive-name', default='Helium-Fork-arm64.zip')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--notary-profile', help='Existing notarytool Keychain profile')
    mode.add_argument('--sign-only', action='store_true', help='Leave notarization pending')
    parser.add_argument('--plan-only', action='store_true', help='Validate inputs without signing')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Fa-f0-9]{40}', args.identity):
        parser.error('--identity must be a certificate fingerprint, never ad-hoc signing')
    if not re.fullmatch(r'[A-Z0-9]{10}', args.team_id):
        parser.error('Invalid Apple Team ID')
    if not re.fullmatch(r'[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+', args.bundle_id):
        parser.error('Invalid bundle identifier')
    if not re.fullmatch(r'[A-Za-z0-9._-]+', args.profile_dir):
        parser.error('Profile directory must be a single directory name')
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9 -]{0,63}', args.app_name):
        parser.error('App name must contain only letters, digits, spaces or hyphens')
    if args.build_number is not None and args.build_number < 1:
        parser.error('Build number must be positive')
    if args.feed_url and not args.feed_url.startswith('https://'):
        parser.error('The update feed must use HTTPS')
    if not re.fullmatch(r'[A-Za-z0-9._-]+\.zip', args.archive_name):
        parser.error('Archive name must be a ZIP filename')

    source = args.chromium_src.resolve()
    source_app = args.source_app.resolve()
    output = args.output_dir.resolve()
    if not (source_app / 'Contents/MacOS/Helium').is_file():
        parser.error('Source must be a built Helium application')
    source_info = plistlib.loads((source_app / 'Contents/Info.plist').read_bytes())
    if args.feed_url:
        if not args.public_key or source_info.get('SUPublicEDKey') != args.public_key:
            parser.error('The built app does not contain the expected Sparkle public key')
        if not (source_app / 'Contents/Frameworks/Helium Framework.framework/Frameworks/Sparkle.framework').exists():
            parser.error('The built app does not contain Sparkle')
        if not args.build_number:
            parser.error('An updater release requires --build-number')
    if output.exists():
        parser.error('Output directory already exists; refusing to replace it')
    identities = run('/usr/bin/security', 'find-identity', '-v', '-p', 'codesigning', capture=True)
    matching = [line for line in identities.splitlines() if args.identity.upper() in line]
    if len(matching) != 1 or 'Developer ID Application:' not in matching[0]:
        parser.error('The specified Developer ID Application identity is not available')
    if f'({args.team_id})' not in matching[0]:
        parser.error('Certificate does not belong to the requested team')

    output.mkdir(parents=True)
    app = output / f'{args.app_name}.app'
    run('/usr/bin/ditto', source_app, app)
    configure_bundle(app, args.bundle_id, args.profile_dir, args.build_number, args.feed_url,
                     args.app_name)
    plan = signing_plan(source, source_app, app, args.bundle_id)
    if args.plan_only:
        print(f'Validated {len(plan)} signing objects; app staged but not signed')
        return

    for name, path, part, entitlements in plan:
        command = ['/usr/bin/codesign', '--force', '--sign', args.identity, '--timestamp']
        if part.sign_with_identifier:
            command += ['--identifier', args.bundle_id + '.' + name]
        if part.options:
            command += ['--options', part.options.to_comma_delimited_string()]
        if entitlements:
            command += ['--entitlements', str(entitlements)]
        run(*command, path)
    run('/usr/bin/codesign', '--verify', '--deep', '--strict', '--verbose=2', app)
    details = subprocess.run(
        ['/usr/bin/codesign', '-dvvv', '-r-', str(app)], check=True, capture_output=True, text=True)
    signature = details.stderr + details.stdout
    if f'TeamIdentifier={args.team_id}' not in signature or 'Signature=adhoc' in signature:
        raise RuntimeError('Unexpected output signing identity')
    (output / 'signature.txt').write_text(signature)

    notarized = False
    if args.notary_profile:
        submission = output / 'notarization-upload.zip'
        run('/usr/bin/ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', app, submission)
        response = run('/usr/bin/xcrun',
                       'notarytool',
                       'submit',
                       submission,
                       '--keychain-profile',
                       args.notary_profile,
                       '--wait',
                       '--output-format',
                       'json',
                       capture=True)
        (output / 'notarization.json').write_text(response)
        if json.loads(response).get('status') != 'Accepted':
            raise RuntimeError('Apple did not accept notarization; see notarization.json')
        run('/usr/bin/xcrun', 'stapler', 'staple', app)
        run('/usr/bin/xcrun', 'stapler', 'validate', app)
        run('/usr/bin/codesign', '--verify', '--deep', '--strict', app)
        run('/usr/sbin/spctl', '--assess', '--type', 'execute', '--verbose=2', app)
        notarized = True
        submission.unlink()

    archive = output / args.archive_name
    run('/usr/bin/ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', app, archive)
    hasher = hashlib.sha256()
    with archive.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(chunk)
    digest = hasher.hexdigest()
    archive.with_suffix('.sha256').write_text(f'{digest}  {archive.name}\n')
    info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
    metadata = {
        'app': str(app),
        'source_app': str(source_app),
        'bundle_id': args.bundle_id,
        'profile_directory': args.profile_dir,
        'team_id': args.team_id,
        'certificate_sha1': args.identity.upper(),
        'version': info['CFBundleVersion'],
        'display_version': info.get('CFBundleShortVersionString'),
        'feed_url': info.get('SUFeedURL'),
        'notarized': notarized,
        'archive_sha256': digest
    }
    (output / 'package-metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print(json.dumps(metadata, indent=2))


if __name__ == '__main__':
    main()
