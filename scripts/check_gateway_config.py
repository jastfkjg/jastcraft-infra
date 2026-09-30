"""Reject missing or conflicting domains and mutable images before touching the gateway."""
import json
import re
import sys
from validate_image import image_reference

def validate(config):
    service = config['services']['caddy']
    image_reference(service['image'])
    env = service['environment']
    domains = [value.removeprefix('http://') for key, value in env.items() if key.endswith('_DOMAIN') or key == 'ECHOOO_ADDRESS']
    if not domains or any(not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9.-]*', value) for value in domains):
        raise ValueError('Use plain hostnames (ECHOOO_ADDRESS may retain a legacy http:// address)')
    if len({d.lower() for d in domains}) != len(domains):
        raise ValueError('Each service must have its own hostname')
    if not re.fullmatch(r'[^\s@]+@[^\s@]+', env.get('ACME_EMAIL','')):
        raise ValueError('Set a certificate contact email')
    for volume in config['volumes'].values():
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]*', volume['name']):
            raise ValueError('Invalid external volume name')
    return config

if __name__ == '__main__':
    try:
        validate(json.load(sys.stdin))
    except (ValueError, KeyError, TypeError) as error:
        sys.exit(str(error))
