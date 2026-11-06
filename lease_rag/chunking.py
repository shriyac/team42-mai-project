"""Clause-aware PDF extraction with exact normalized-page citation spans.

Refactored from the notebook; importing this module performs no ingestion.
"""
from pathlib import Path
from copy import deepcopy
from hashlib import sha256
from importlib.metadata import version
import json
import math
import re
from pypdf import PdfReader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

CHUNKER_VERSION = 'langchain-clause-aware-v3-tenant'
NORMALIZATION_VERSION = 'layout-lines-v1'
TARGET_CHARS = 1800
MAX_TOKENS = 700
OVERLAP_CHARS = 240

def token_estimate(text):
    return math.ceil(len(re.findall(r"\w+|[^\w\s]", text)) * 1.35)

FOOTER = re.compile(r'^NC General Statutes\s*[-–]\s*Chapter\s+42\s+(\d+)\s*$')

def extract_document(path, config, root):
    reader = PdfReader(path)
    digest = sha256(path.read_bytes()).hexdigest()
    doc_id = config['document_id']
    warnings = list(config.get('warnings', []))
    if not config:
        warnings.append('Unconfigured document: confirm type, jurisdiction, applicability and access scope.')
    pages = []
    full_text = ''
    for index, page in enumerate(reader.pages):
        raw = page.extract_text(extraction_mode='layout') or ''
        lines = []
        printed_label = None
        for line in raw.splitlines():
            line = re.sub(r'[^\S\n]+', ' ', line).strip()
            # Explicitly configured repeating banners are provenance, not clause text.
            # Their meaning is retained in document status and review warnings.
            if line in config.get('repeated_header_footer_lines', []):
                continue
            footer = FOOTER.fullmatch(line)
            if footer:
                printed_label = footer.group(1)
                continue
            lines.append(line)
        text = re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).strip()
        issues = []
        if len(text) < 40:
            issues.append('Very little extracted text; inspect for scanned or blank content.')
        if page.get('/Annots'):
            issues.append('PDF annotations/widgets present; review visual marks and field values.')
        if '\ufffd' in text:
            issues.append('Replacement character detected; inspect extraction quality.')
        start = len(full_text)
        full_text += text + '\n\n'
        pages.append({
            'document_id': doc_id, 'page_number': index + 1,
            'printed_page_label': printed_label, 'text': text,
            'document_char_start': start, 'document_char_end': start + len(text),
            'extraction_method': 'pypdf.layout',
            'normalization_version': NORMALIZATION_VERSION,
            'needs_review': bool(issues), 'warnings': issues,
        })
    form_fields = reader.get_fields() or {}
    fields = [{
        'name': name, 'type': str(field.get('/FT', '')),
        'value': str(field['/V']) if '/V' in field else None,
    } for name, field in form_fields.items()]
    if fields:
        warnings.append('Interactive form values stored separately; reconcile with text before answering.')
    for page in pages:
        warnings.extend(f"Page {page['page_number']}: {issue}" for issue in page['warnings'])
    kind = config.get('document_type')
    if kind is None:
        kind = 'statute' if re.search(r'^§\s+\d+-', full_text, re.M) else 'lease'
    document = {
        'document_id': doc_id, 'document_sha256': digest,
        'document_version': digest, 'source_filename': path.name,
        'source_uri': path.relative_to(root).as_posix(),
        'document_title': config.get('document_title', path.stem),
        'document_type': kind,
        'document_status': config.get('document_status', 'unknown'),
        'jurisdiction': config.get('jurisdiction'),
        'lease_id': config.get('lease_id'), 'property_id': config.get('property_id'),
        'access_scope_id': config.get('access_scope_id'),
        'effective_from': config.get('effective_from'), 'effective_to': config.get('effective_to'),
        'supersedes_document_id': config.get('supersedes_document_id'),
        'page_count': len(pages), 'parser_version': 'pypdf-' + version('pypdf'),
        'normalization_version': NORMALIZATION_VERSION,
        'form_fields': fields, 'needs_review': bool(warnings), 'warnings': warnings,
    }
    return {'metadata': document, 'pages': pages, 'text': full_text.rstrip()}

def source_spans(doc, start, end):
    """Exact, end-exclusive slices of the immutable normalized page records."""
    spans = []
    for page in doc['pages']:
        a = max(start, page['document_char_start'])
        b = min(end, page['document_char_end'])
        if a < b:
            spans.append({
                'page_number': page['page_number'],
                'printed_page_label': page['printed_page_label'],
                'char_start': a - page['document_char_start'],
                'char_end': b - page['document_char_start'],
                'text': doc['text'][a:b],
            })
    return spans


STATUTE_HEADING = re.compile(
    r'^§{1,2}\s+(\d+-\d+[A-Za-z]?(?:\.\d+[A-Za-z]?)?'
    r'(?: through \d+-\d+(?:\.\d+)?)?)[.:]\s+(.+)')
LEASE_HEADING = re.compile(r'^(\d+)\.\s+([A-Z][A-Z &/’\x27-]+)\.')
ARTICLE_HEADING = re.compile(r'^Article (\d+[A-Z]?)\.$')

def line_records(text):
    return [(m.start(), m.group()) for m in re.finditer(r'[^\n]+', text)]

def build_nodes(doc):
    text = doc['text']
    statute = doc['metadata']['document_type'] == 'statute'
    lines = line_records(text)
    boundaries = []
    article = None
    for i, (start, line) in enumerate(lines):
        article_match = ARTICLE_HEADING.fullmatch(line) if statute else None
        if article_match:
            article = article_match.group(1)
            title = lines[i + 1][1] if i + 1 < len(lines) else ''
            boundaries.append((start, 'article-' + article, f'Article {article}. {title}', article, 'article'))
            continue
        match = (STATUTE_HEADING if statute else LEASE_HEADING).match(line)
        if match:
            section, title = match.groups()
            if statute and not title.endswith('.'):
                # Wrapped statute titles end in a period before the body begins.
                j = i + 1
                while j < len(lines) and not title.endswith('.'):
                    if re.match(r'^(?:§|\(|Article \d)', lines[j][1]):
                        break
                    title += ' ' + lines[j][1]
                    j += 1
            boundaries.append((start, section, title.rstrip('.'), article, 'section'))
        elif not statute and line in ('AMOUNT DUE AT SIGNING',):
            boundaries.append((start, 'signing-summary', line, None, 'summary'))
        elif not statute and line.startswith('IN WITNESS WHEREOF'):
            boundaries.append((start, 'signatures', 'Signatures', None, 'signatures'))
    if not boundaries:
        doc['metadata']['warnings'].append('No recognized sections; using document-level fallback. Review layout.')
        doc['metadata']['needs_review'] = True
    if not boundaries or boundaries[0][0] > 0:
        boundaries.insert(0, (0, 'preamble', 'Document preamble', None, 'preamble'))
    nodes = []

    def new_node(start, end, section, title, article, kind, parent=None, marker=None):
        clause_path = (parent['clause_path'] + [marker]) if parent and marker else []
        node_id = f"{doc['metadata']['document_id']}:node:{start}"
        heading = f'§ {section}. {title}' if statute and kind == 'section' else title
        node = {
            'node_id': node_id, 'parent_node_id': parent['node_id'] if parent else None,
            'section_id': section, 'section_title': parent['section_title'] if parent else title,
            'node_title': title, 'article_id': article, 'kind': kind,
            'clause_path': clause_path,
            'clause_id': section + ''.join(f'({x})' for x in clause_path) if clause_path else None,
            'heading_path': parent['heading_path'] + [title] if parent else (
                ([f'Article {article}'] if article and kind == 'section' else []) + [heading]
            ),
            'start': start, 'end': end, 'children': [],
        }
        nodes.append(node)
        if parent:
            parent['children'].append(node)
        return node

    for i, (start, section, title, article, kind) in enumerate(boundaries):
        end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(text)
        root = new_node(start, end, section, title, article, kind)
        if kind != 'section':
            continue
        stack = [(0, root)]
        for pos, line in lines:
            if pos <= start or pos >= end:
                continue
            level = None
            marker = None
            if statute:
                match = re.match(r'^\(([a-z]+\d*|\d+[a-z]?)\)\s+(.+)', line)
                if match:
                    marker = match.group(1)
                    level = 1 if marker[0].isalpha() else 2
                else:
                    match = re.match(r'^([a-z])\.\s+(.+)', line)
                    if match:
                        marker, level = match.group(1), 3
            else:
                for pattern, candidate_level in [
                    (r'^([a-z])\.\)\s+(.+)', 1),
                    (r'^([ivxlcdm]+)\.\s+(.+)', 2),
                    (r'^(\d+)\)\s+(.+)', 3),
                ]:
                    match = re.match(pattern, line)
                    if match:
                        marker, level = match.group(1), candidate_level
                        break
            if level is None:
                continue
            while stack[-1][0] >= level:
                stack.pop()[1]['end'] = pos
            parent = stack[-1][1]
            # Statute subsections generally lack named titles; retain their marker.
            label = f'({marker})' if statute else f"{marker}. {match.group(2).split('.')[0]}"
            child = new_node(pos, end, section, label, article, 'clause', parent, marker)
            stack.append((level, child))
    return nodes


def trim_span(text, start, end):
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end

# Sentence boundaries come after paragraph/line boundaries. Keep separators so
# every returned Document.page_content is an exact substring of its source.
leaf_splitter = RecursiveCharacterTextSplitter(
    chunk_size=TARGET_CHARS,
    chunk_overlap=OVERLAP_CHARS,
    length_function=len,
    separators=[r"\n\n", r"\n", r"(?<=[.!?;])\s+", r" ", ""],
    is_separator_regex=True,
    keep_separator="end",
    add_start_index=True,
    strip_whitespace=False,
)

def split_long_span(text, start, end):
    """Use LangChain within a leaf, then restore global citation offsets."""
    start, end = trim_span(text, start, end)
    if start == end:
        return []
    if token_estimate(text[start:end]) <= MAX_TOKENS:
        return [(start, end)]
    source = text[start:end]
    pieces = leaf_splitter.create_documents([source])
    spans = []
    for piece in pieces:
        local_start = piece.metadata['start_index']
        assert local_start >= 0, 'Splitter could not locate a source span.'
        local_end = local_start + len(piece.page_content)
        assert source[local_start:local_end] == piece.page_content
        a, b = trim_span(text, start + local_start, start + local_end)
        if a < b:
            spans.append((a, b))
    return spans


def blank_fields(text):
    # Every detected blank carries its source line; no monetary values are inferred.
    return [{'status': 'blank', 'source_line': line}
            for line in text.splitlines() if re.search(r'_{2,}', line)]

def pet_field_states(text):
    fields = {}
    for name, pattern in {
        'maximum_pet_weight_lb': r'Maximum Weight\s*\(per pet\):\s*(_+|[\d.]+)\s*Pounds',
        'pet_deposit_amount': r'Deposit\s*\(for all pets\):\s*\$(_+|[\d,.]+)',
        'number_of_pets': r'Number of Pets:\s*(_+|\d+)',
    }.items():
        m = re.search(pattern, text, re.I)
        if m:
            raw = m.group(1)
            fields[name] = {'status': 'blank' if '_' in raw else 'present',
                            'raw_value': raw, 'value': None if '_' in raw else float(raw.replace(',', ''))}
    for name, labels in {
        'pets_allowed': [r'No Pets Allowed', r'Pets are Allowed'],
        'pet_deposit_refundable': [r'refundable', r'non-refundable'],
    }.items():
        marks = [re.search(r'([☐☑☒])\s*(?:-\s*)?' + label + r'\b', text, re.I) for label in labels]
        if all(marks):
            selected = [i for i, m in enumerate(marks) if m.group(1) in '☑☒']
            fields[name] = {
                'status': 'unselected' if not selected else ('selected' if len(selected) == 1 else 'conflicting'),
                'value': (selected[0] == (1 if name == 'pets_allowed' else 0)) if len(selected) == 1 else None,
                'detection_method': 'extracted_text_glyphs_only',
            }
    return fields

def references(text):
    results = []
    for m in re.finditer(r'\b[Ss]ection\s+(\d+)\b', text):
        results.append({'type': 'lease_section', 'target_section_id': m.group(1)})
    for m in re.finditer(r'(?:G\.S\.|§)\s*(\d+-\d+(?:\.\d+)?[A-Za-z]?)(\([a-z0-9]+\))?', text):
        results.append({'type': 'statute', 'target_section_id': m.group(1), 'subsection': m.group(2)})
    return list({json.dumps(x, sort_keys=True): x for x in results}.values())

def build_chunks(doc):
    chunks = []
    text = doc['text']
    meta = doc['metadata']

    def emit(node, start, end, context):
        for a, b in split_long_span(text, start, end):
            body = text[a:b]
            spans = source_spans(doc, a, b)
            identity = f"{meta['document_id']}:{meta['tenant_name']}:{meta['document_sha256']}:{CHUNKER_VERSION}:{TARGET_CHARS}:{MAX_TOKENS}:{OVERLAP_CHARS}:{a}:{b}"
            chunk_id = 'chunk-' + sha256(identity.encode()).hexdigest()[:24]
            fields = pet_field_states(body)
            pages = sorted({s['page_number'] for s in spans})
            breadcrumb = ' > '.join([meta['document_title']] + node['heading_path'])
            embedded = '\n\n'.join([breadcrumb] + [c['text'] for c in context] + [body])
            location = node['clause_id'] or node['section_id']
            chunk_meta = {k: meta[k] for k in (
                'tenant_name', 'tenant_display_name', 'access', 'document_id', 'document_sha256', 'document_version', 'source_filename', 'source_uri',
                'document_title', 'document_type', 'document_status', 'jurisdiction', 'lease_id',
                'property_id', 'access_scope_id', 'effective_from', 'effective_to', 'parser_version',
                'normalization_version', 'supersedes_document_id',
            )}
            chunk_meta.update({
                'node_id': node['node_id'], 'parent_node_id': node['parent_node_id'],
                'section_id': node['section_id'], 'section_title': node['section_title'],
                'article_id': node['article_id'], 'clause_id': node['clause_id'],
                'clause_path': node['clause_path'], 'heading_path': node['heading_path'],
                'page_numbers': pages,
                'printed_page_labels': [s['printed_page_label'] for s in spans],
                'document_char_start': a, 'document_char_end': b,
                'source_spans': spans,
                'citation_label': f"{meta['source_filename']}, PDF p. {', '.join(map(str, pages))}, {location}",
                'cross_references': references(body), 'related_chunk_ids': [], 'relationships': [],
                'has_unfilled_fields': bool(blank_fields(body)), 'blank_fields': blank_fields(body),
                'field_states': fields,
                'checkbox_detection': 'text_glyphs_only',
                'needs_review': meta['needs_review'] or any(v['status'] == 'conflicting' for v in fields.values()),
                'chunker_version': CHUNKER_VERSION,
                'body_token_estimate': token_estimate(body),
                'embedding_token_estimate': token_estimate(embedded),
                'token_count_method': 'regex_units_times_1.35_estimate',
                'embedding_model': None, 'embedding_dimensions': None,
                'index_role': 'reference_structure' if node['kind'] in ('article', 'preamble', 'signatures') else 'retrieval',
            })
            chunks.append({'chunk_id': chunk_id, 'source_text': body,
                           'context': context, 'embedding_text': embedded, 'metadata': chunk_meta})

    def visit(node, context):
        a, b = trim_span(text, node['start'], node['end'])
        if token_estimate(text[a:b]) <= MAX_TOKENS or not node['children']:
            emit(node, a, b, context)
            return
        intro_end = node['children'][0]['start']
        x, y = trim_span(text, a, intro_end)
        extra = []
        if x < y:
            intro = text[x:y]
            extra = [{'node_id': node['node_id'], 'text': intro, 'source_spans': source_spans(doc, x, y)}]
            # Also retain introductory text as its own searchable evidence.
            emit(node, x, y, context)
        for child in node['children']:
            visit(child, context + extra)

    for node in doc['nodes']:
        if node['parent_node_id'] is None:
            visit(node, [])
    return chunks



def chunk_pdf(path, config, root):
    """Return LangChain Documents and a provenance report for one declared PDF."""
    doc = extract_document(path, config, root)
    if not doc['text'].strip():
        raise ValueError(f'{path.name}: no extractable text; OCR is required before ingestion.')
    doc['metadata'].update({key: config[key] for key in
                            ('tenant_name', 'tenant_display_name', 'access')})
    doc['nodes'] = build_nodes(doc)
    result = []
    for chunk in build_chunks(doc):
        # Include preambles and unrecognized formats: arbitrary uploaded leases
        # must not disappear merely because their headings differ from the sample.
        metadata = deepcopy(chunk['metadata'])
        metadata.update(chunk_id=chunk['chunk_id'], source_text=chunk['source_text'],
                        context=chunk['context'], warnings=doc['metadata']['warnings'])
        result.append(Document(page_content=chunk['embedding_text'], metadata=metadata))
    if not result:
        raise ValueError(f'{path.name}: extraction produced no chunks.')
    return result, doc['metadata']
