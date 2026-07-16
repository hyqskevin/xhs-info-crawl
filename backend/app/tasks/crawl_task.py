from datetime import datetime,timezone
from sqlalchemy import select
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.activity import Activity
from app.models.note import Note,NoteImage
from app.models.task import CrawlTask,TaskLog
from app.services.crawler import AuthenticationRequired
from app.services.extraction import extract_activity_fields
from app.services.dedup import create_duplicate_candidates
from app.services.minimax import MiniMaxClient
from app.services.opencli_adapter import OpenCLIAdapter
from app.services.ocr import OCRService
from app.services.paddleocr_adapter import PaddleOCREngine
from app.tasks.celery_app import celery_app

def log(db,task_id,level,message): db.add(TaskLog(task_id=task_id,level=level,message=message)); db.commit()
@celery_app.task(name='app.tasks.crawl_task.run',bind=True,max_retries=3)
def run_crawl(self,task_id:int):
    db=SessionLocal(); task=db.get(CrawlTask,task_id); settings=get_settings(); adapter=OpenCLIAdapter(settings)
    try:
        task.status='RUNNING'; task.started_at=datetime.now(timezone.utc); db.commit(); log(db,task.id,'INFO','login check')
        results=[]
        for city in task.params.get('cities',[]):
            for keyword in task.params.get('keywords',[]): results.extend((city,x) for x in adapter.search_recent(f'{city} {keyword}'))
        task.status='DOWNLOADING'; task.total_notes=len(results); db.commit()
        for city,item in results:
            if db.scalar(select(Note).where(Note.source_url==item['url'])): continue
            detail=adapter.note(item['url']); note=Note(task_id=task.id,platform_note_id=item['url'].split('/')[-1].split('?')[0],title=item.get('title',''),content=detail.get('content',''),source_url=item['url'],city_code=city,status='DOWNLOADED',raw_data=detail); db.add(note); db.flush()
            images=adapter.download(item['url'],settings.image_dir/note.platform_note_id)
            ocr_texts=[]
            ocr=OCRService(PaddleOCREngine(settings),settings.ocr_min_confidence) if settings.ocr_enabled else None
            for image in images:
                result=ocr.process(image) if ocr else {'status':'disabled','text':'','error':''}
                db.add(NoteImage(note_id=note.id,storage_key=str(image.relative_to(settings.image_dir)),ocr_text=result['text'],ocr_status=result['status'],ocr_error=result['error']))
                if result['text']: ocr_texts.append(result['text'])
            note.status='OCR_DONE' if ocr else 'DOWNLOADED'
            combined=f"{note.title}\n{note.content}\n"+'\n'.join(ocr_texts); fields=extract_activity_fields(combined,datetime.now(),MiniMaxClient(settings).extract if settings.minimax_api_key else None)
            activity=Activity(name=fields.get('name') or note.title,city_code=city,start_time=datetime.fromisoformat(fields['start_time']) if fields.get('start_time') else datetime.now(timezone.utc),location=fields.get('location') or '',price=fields.get('price') or '',type=fields.get('type') or '其他',source_url=note.source_url,summary=note.content[:300],status=fields['status']); db.add(activity); db.flush(); create_duplicate_candidates(db,activity)
            task.success_notes+=1; db.commit()
        task.status='COMPLETED'; task.finished_at=datetime.now(timezone.utc); db.commit(); log(db,task.id,'INFO','completed')
    except AuthenticationRequired as exc:
        task.status='PAUSED'; task.error_message=str(exc); db.commit(); log(db,task.id,'ERROR',str(exc))
    except Exception as exc:
        task.status='FAILED'; task.error_message=str(exc); db.commit(); log(db,task.id,'ERROR',str(exc)); raise self.retry(exc=exc,countdown=300)
    finally: db.close()
