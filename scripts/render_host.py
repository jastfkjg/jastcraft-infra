"""Render only the selected host's routes and local Docker networks; no dependencies."""
import argparse
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SERVICES = {'echooo': 'ECHOOO_ADDRESS', 'shadowtable': 'SHADOWTABLE_DOMAIN', 'wenlv': 'WENLV_DOMAIN', 'just-works': 'JUST_WORKS_DOMAIN', 'inkmind': 'INKMIND_DOMAIN', 'directo': 'DIRECTO_DOMAIN'}


def load_host(selector, root=ROOT):
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]*', selector):
        raise ValueError('Select a host target ID from hosts/**/host.json')
    matches = []
    for path in sorted((root / 'hosts').glob('*/*/*/host.json')):
        config = json.loads(path.read_text())
        if config.get('target') == selector:
            matches.append((path, config))
    if len(matches) != 1:
        raise ValueError('Unknown or duplicate host target: ' + selector)
    path, config = matches[0]
    cloud, location, number = path.relative_to(root / 'hosts').parts[:3]
    if (cloud not in {'aws', 'aliyun'} or config['cloud'] != cloud
            or config['location'] != location or not re.fullmatch(r'[a-z0-9]+', location)
            or not re.fullmatch(r'[0-9]{2}', number) or selector != f'{cloud}-{location}-{number}'):
        raise ValueError('Host target must match its cloud/location/number directory')
    if config['environment'] not in {'prod', 'staging'}:
        raise ValueError('Configure the application environment separately from the host location')
    if not re.fullmatch(r'[a-z][a-z0-9-]+', config['region']):
        raise ValueError('Configure the cloud region for this host')
    services = config['services']
    if not services or len(set(services)) != len(services) or any(s not in SERVICES for s in services):
        raise ValueError('Configure a nonempty, unique list of supported services')
    return path.parent, config


def render(selector, output, gateway_root='/opt/gateway', root=ROOT):
    _, host = load_host(selector, root)
    if not Path(gateway_root).is_absolute():
        raise ValueError('Gateway root must be absolute')
    services = host['services']
    environment = {'ACME_EMAIL': '${ACME_EMAIL:?Set certificate contact email}'}
    environment.update({SERVICES[s]: '${' + SERVICES[s] + ':?Set domain for this host}' for s in services})
    compose = {
        'name': 'jastcraft-gateway',
        'services': {'caddy': {
            'image': '${CADDY_IMAGE:?Set an immutable Caddy image}', 'restart': 'unless-stopped',
            'environment': environment, 'ports': ['80:80', '443:443'],
            'volumes': [gateway_root + '/config:/etc/caddy:ro', 'caddy_data:/data', 'caddy_config:/config'],
            'networks': services,
            'healthcheck': {'test':['CMD','wget','-q','-O','/dev/null','http://127.0.0.1:2019/config/'], 'interval':'5s','timeout':'3s','retries':12},
            'logging': {'driver':'json-file','options':{'max-size':'10m','max-file':'3'}}
        }},
        'networks': {s:{'external':True,'name':s+'_proxy'} for s in services},
        'volumes': {
            'caddy_data': {'external':True,'name':'${CADDY_DATA_VOLUME:?Set host certificate volume}'},
            'caddy_config': {'external':True,'name':'${CADDY_CONFIG_VOLUME:?Set host config volume}'}
        }
    }
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    # JSON is a YAML subset and avoids introducing a Python YAML runtime dependency.
    (output / 'compose.yaml').write_text(json.dumps(compose, indent=2)+'\n')
    routes = ['{\n    email {$ACME_EMAIL}\n}\n']
    routes += [(root/'gateway/routes'/f'{s}.caddy').read_text() for s in services]
    (output/'Caddyfile').write_text('\n'.join(routes))
    (output/'host').write_text(selector+'\n')
    return compose


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('target')
    parser.add_argument('output')
    parser.add_argument('--gateway-root', default='/opt/gateway')
    args = parser.parse_args()
    try:
        render(args.target, args.output, args.gateway_root)
    except (ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
