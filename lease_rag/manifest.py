"""Document ownership comes from an operator-maintained manifest, never PDF text."""
from pathlib import Path
import json
import unicodedata


def tenant_key(name):
    if not isinstance(name, str) or not name.strip():
        raise ValueError('A nonempty tenant name is required.')
    return ' '.join(unicodedata.normalize('NFKC', name).casefold().split())


def read_manifest(path, data_dir):
    data_dir = Path(data_dir).resolve()
    records = json.loads(Path(path).read_text(encoding='utf-8'))['documents']
    if not isinstance(records, list) or not records:
        raise ValueError('Manifest must contain a nonempty documents list.')
    result, identities, paths = [], set(), set()
    for record in records:
        item = dict(record)
        relative = Path(item['path'])
        pdf = (data_dir / relative).resolve()
        if relative.is_absolute() or not pdf.is_relative_to(data_dir):
            raise ValueError('Manifest paths must be relative paths inside data/.')
        if not pdf.is_file() or pdf.suffix.lower() != '.pdf':
            raise ValueError(f'Missing PDF: {pdf}')
        doc_id = item.get('document_id', '')
        if not isinstance(doc_id, str) or not doc_id.strip() or len(doc_id) > 100:
            raise ValueError('Each document needs a nonempty document_id of at most 100 characters.')
        if doc_id != doc_id.strip() or doc_id in identities or pdf in paths:
            raise ValueError('Document IDs and PDF paths must be unique, with no surrounding whitespace.')
        access = item.get('access', 'tenant')
        is_statute = pdf.name.casefold() == 'nc_general_statutes_chapter_42.pdf'
        if access == 'shared':
            if not is_statute or item.get('tenant_name'):
                raise ValueError('Only NC_general_statutes_Chapter_42.pdf may be shared, without a tenant name.')
            item.update(tenant_name='', tenant_display_name='', document_type='statute',
                        document_status='reference_snapshot')
        elif access == 'tenant' and not is_statute:
            display_name = item.get('tenant_name')
            item['tenant_name'] = tenant_key(display_name)
            item['tenant_display_name'] = display_name.strip()
            item.setdefault('document_type', 'lease')
            item.setdefault('document_status', 'unknown')
            if item['document_type'] not in ('lease', 'lease_template'):
                raise ValueError('Tenant documents must be leases or lease templates.')
        else:
            raise ValueError('Use access=tenant for leases and access=shared for NC Chapter 42.')
        item.update(access=access, pdf_path=pdf)
        item.setdefault('jurisdiction', 'US-NC')
        identities.add(doc_id)
        paths.add(pdf)
        result.append(item)
    discovered = {p.resolve() for p in data_dir.rglob('*') if p.is_file() and p.suffix.lower() == '.pdf'}
    if discovered - paths:
        missing = ', '.join(str(p.relative_to(data_dir)) for p in sorted(discovered - paths))
        raise ValueError(f'Assign ownership to every PDF in the manifest before ingestion. Unassigned: {missing}')
    return result
