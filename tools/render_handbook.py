"""Generate/check the human traceability matrix from the runtime registry."""
from pathlib import Path
from installer.handbook import REQUIREMENTS, ALTERNATIVES, REFERENCE, REVIEWED

ROOT = Path(__file__).resolve().parents[1]


def render():
    lines = ['# AMD64 Handbook traceability', '', f'Reference: {REFERENCE}. Retrieved in full via HTTPS on {REVIEWED}.', '',
             'The selected path is UEFI/GPT, OpenRC multilib, Btrfs, distribution kernel/dracut and GRUB.',
             'Implemented, unit-tested, integration-verified, VM-verified and hardware-verified are distinct states.',
             'Test file references identify coverage; retained run evidence proves actual execution.',
             'No hardware verification or complete installed-system boot is currently claimed.', '',
             '| ID | Handbook area | Applicable behavior | Implementation | Automated coverage | Verification procedure | Current evidence |',
             '|---|---|---|---|---|---|---|']
    for item in REQUIREMENTS:
        lines.append('| ' + ' | '.join((item.key, item.section, item.behavior, item.implementation or 'Pending',
                                       item.tests or 'Pending', item.verification, item.status)) + ' |')
    lines += ['', '## Alternatives and optional choices', '']
    lines += [f'- **{key}:** {value}.' for key, value in ALTERNATIVES.items()]
    lines += ['', '## Evidence boundary', '',
              'The recorded Gentoo UEFI VM storage run passed, including an unchanged entire NTFS fixture hash.',
              'The Chromebook minimal attempt stopped during Stage3 extraction after host memory pressure.',
              'Remote run 42506097798 completed extraction, then failed at missing offline DNS configuration; no installed boot was recorded.',
              'Current remote qualification procedure and limitations: [MINIMAL-VM.md](MINIMAL-VM.md).',
              'The machine-readable registry is `python -m installer.handbook`. Its completion flag stays false while required stages lack VM evidence.',
              'Regenerate this file with `python -m tools.render_handbook`; CI checks it remains synchronized.', '']
    return '\n'.join(lines)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    arguments = parser.parse_args()
    target = ROOT / 'docs/HANDBOOK-COVERAGE.md'
    if arguments.check:
        if not target.is_file() or target.read_text() != render():
            parser.exit(1, 'Handbook matrix is out of sync; run python -m tools.render_handbook\n')
    else:
        target.write_text(render())
