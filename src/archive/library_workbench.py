"""Local editorial decisions and citation-preserving investigation folders."""
import json
import uuid
from datetime import date
from archive.document_library import now, encoded
from archive.library_editorial import EditorialDesk, saved_editorial


def field(value, label, maximum, required=False):
    if not isinstance(value, str) or len(value)>maximum or (required and not value.strip()):
        raise ValueError(f'Enter a valid {label} (up to {maximum} characters)')
    return value.strip()


class Workbench:
    def __init__(self,library):
        self.library=library; self.db=library.db
        EditorialDesk(library)
        self.db.executescript('''CREATE TABLE IF NOT EXISTS library_editor_reviews (
            id INTEGER PRIMARY KEY, document_id TEXT NOT NULL, title TEXT NOT NULL,
            summary TEXT NOT NULL, note TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS library_editor_reviews_doc ON library_editor_reviews(document_id,id);
            CREATE TABLE IF NOT EXISTS library_folders (
            id TEXT PRIMARY KEY,title TEXT NOT NULL,question TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS library_folder_items (
            id TEXT PRIMARY KEY,folder_id TEXT NOT NULL REFERENCES library_folders(id),
            payload_json TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'open',created_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS library_folder_items_folder ON library_folder_items(folder_id,created_at);''')

    def queue(self,reason='uncertain',status='open',offset=0):
        reasons={'uncertain':"e.document_id IS NOT NULL AND json_extract(e.result_json,'$.status')='Needs editorial review'",
            'ocr':"EXISTS(SELECT 1 FROM library_pages p WHERE p.document_id=d.id AND p.needs_ocr=1)",
            'publication':'d.public=0'}
        if reason not in reasons or status not in {'open','reviewed','deferred','all'}: raise ValueError('Invalid review filter')
        offset=max(0,int(offset))
        sql=''' FROM library_documents d
            LEFT JOIN library_editorial e ON e.rowid=(SELECT max(x.rowid) FROM library_editorial x WHERE x.document_id=d.id)
            LEFT JOIN library_editor_reviews r ON r.id=(SELECT max(x.id) FROM library_editor_reviews x WHERE x.document_id=d.id)
            WHERE d.extraction_status!='quarantined' AND '''+reasons[reason]
        params=[]
        if status!='all': sql+=" AND coalesce(r.status,'open')=?"; params.append(status)
        total=self.db.execute('SELECT count(*)'+sql,params).fetchone()[0]
        rows=self.db.execute("SELECT d.id,d.title,d.collection,d.public,coalesce(r.status,'open') AS status"+sql+' ORDER BY d.retrieved_at,d.id LIMIT 25 OFFSET ?',[*params,offset]).fetchall()
        return dict(total=total,offset=offset,items=[dict(r) for r in rows])

    def document(self,identifier,page=1):
        doc=self.db.execute("SELECT id,title,source_url,sha256,public FROM library_documents WHERE id=? AND extraction_status!='quarantined'",(identifier,)).fetchone()
        if not doc: raise ValueError('Document unavailable')
        if type(page) is not int or page<1: raise ValueError('Choose a valid page')
        text=self.db.execute('SELECT number,text,needs_ocr FROM library_pages WHERE document_id=? AND number=?',(identifier,page)).fetchone()
        if not text: raise ValueError('Page unavailable')
        review=self.db.execute('SELECT * FROM library_editor_reviews WHERE document_id=? ORDER BY id DESC LIMIT 1',(identifier,)).fetchone()
        history=[dict(r) for r in self.db.execute('SELECT * FROM library_editor_reviews WHERE document_id=? ORDER BY id DESC LIMIT 20',(identifier,))]
        return dict(**dict(doc),page=dict(text),page_count=self.db.execute('SELECT count(*) FROM library_pages WHERE document_id=?',(identifier,)).fetchone()[0],
            editorial=saved_editorial(self.library,identifier),review=dict(review) if review else None,history=history)

    def review(self,values):
        identifier=field(values.get('id'),'document',64,True)
        title=field(values.get('title'),'title',240,True)
        summary=field(values.get('summary'),'brief',1600)
        note=field(values.get('note'),'review note',600,True)
        status=values.get('status')
        if status not in {'reviewed','deferred','open'}: raise ValueError('Invalid review status')
        if type(values.get('revision')) is not int: raise ValueError('Review revision is required')
        if not self.db.execute("SELECT 1 FROM library_documents WHERE id=? AND extraction_status!='quarantined'",(identifier,)).fetchone(): raise ValueError('Document unavailable')
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            last=self.db.execute('SELECT coalesce(max(id),0) FROM library_editor_reviews WHERE document_id=?',(identifier,)).fetchone()[0]
            if last!=values['revision']: raise ValueError('Another review was saved. Reload this document before saving.')
            self.db.execute('INSERT INTO library_editor_reviews(document_id,title,summary,note,status,created_at) VALUES(?,?,?,?,?,?)',(identifier,title,summary,note,status,now()))
        return self.document(identifier)

    def folders(self):
        return [dict(r) for r in self.db.execute('SELECT f.*,count(i.id) AS item_count FROM library_folders f LEFT JOIN library_folder_items i ON i.folder_id=f.id GROUP BY f.id ORDER BY f.created_at DESC')]

    def create_folder(self,values):
        identifier=uuid.uuid4().hex
        with self.db: self.db.execute('INSERT INTO library_folders VALUES(?,?,?,?)',(identifier,field(values.get('title'),'folder title',160,True),field(values.get('question',''),'guiding question',800),now()))
        return self.folder(identifier)

    def folder(self,identifier):
        folder=self.db.execute('SELECT * FROM library_folders WHERE id=?',(identifier,)).fetchone()
        if not folder: raise ValueError('Folder unavailable')
        items=[]
        for row in self.db.execute('SELECT * FROM library_folder_items WHERE folder_id=? ORDER BY created_at,id',(identifier,)):
            item=json.loads(row['payload_json'])
            if item.get('document_id') and not self.library.document(item['document_id'],include_pages=False):
                item=dict(kind=item['kind'],unavailable=True,text='Source is unavailable or withdrawn. Evidence hidden.')
            items.append(dict(**item,id=row['id'],status=row['status'],created_at=row['created_at']))
        return dict(**dict(folder),items=items)

    def add(self,values):
        folder_id=field(values.get('folder_id'),'folder',32,True)
        self.folder(folder_id)
        kind=values.get('kind')
        if kind not in {'document','quote','note','question','hypothesis','event'}: raise ValueError('Invalid evidence type')
        item=dict(kind=kind,text=field(values.get('text',''),'text',1800,kind not in {'document'}),note=field(values.get('note',''),'note',500))
        document_id=values.get('document_id')
        if kind in {'document','quote'} and not document_id: raise ValueError('Choose a published source document')
        if document_id:
            doc=self.library.document(document_id,include_pages=False)
            page=values.get('page',1)
            if type(page) is not int or page<1: raise ValueError('Choose a valid source page')
            source=self.library.page(document_id,page) if doc else None
            if not source: raise ValueError('Published source page unavailable')
            item.update(document_id=document_id,page=page,source_url=doc['source_url'],source_sha256=doc['sha256'],source_title=doc['title'])
            if kind=='quote':
                start=source['text'].find(item['text'])
                if start<0: raise ValueError('The quotation must match the source page exactly')
                if source['text'].find(item['text'],start+1)>=0: raise ValueError('This quotation occurs more than once. Include more surrounding text to identify the passage.')
                item.update(start=start,end=start+len(item['text']))
        if kind=='event':
            try: item['event_date']=date.fromisoformat(values.get('event_date','')).isoformat()
            except (TypeError,ValueError): raise ValueError('Enter a calendar date for this timeline entry') from None
        with self.db: self.db.execute('INSERT INTO library_folder_items VALUES(?,?,?,?,?)',(uuid.uuid4().hex,folder_id,encoded(item),'open',now()))
        return self.folder(folder_id)

    def item_status(self,values):
        if values.get('status') not in {'open','done'}: raise ValueError('Invalid item status')
        with self.db:
            cursor=self.db.execute('UPDATE library_folder_items SET status=? WHERE id=? AND folder_id=?',(values['status'],values.get('id'),values.get('folder_id')))
            if cursor.rowcount!=1: raise ValueError('Folder item unavailable')
        return self.folder(values['folder_id'])

    def markdown(self,identifier):
        folder=self.folder(identifier)
        lines=['# '+folder['title'],'',folder['question'],'','Working investigation notes. Hypotheses and source claims remain unverified.','']
        for item in sorted(folder['items'],key=lambda i:(i.get('event_date','9999'),i['created_at'])):
            lines+=['## '+item['kind'].title()+(' — '+item['event_date'] if item.get('event_date') else ''),'',item.get('text',''),'']
            if item.get('document_id'):
                lines += ['Source: '+item['source_title'],'URL: '+item['source_url'],f"Document: {item['document_id']} | page {item['page']}",'SHA-256: '+item['source_sha256'],'']
            if item.get('note'): lines += ['Note: '+item['note'],'']
            lines += ['Status: '+item['status'],'']
        return '\n'.join(lines)
