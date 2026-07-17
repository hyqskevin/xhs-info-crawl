from datetime import datetime,timezone
import shutil
from sqlalchemy import select
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.activity import Activity
from app.models.config import Blogger, City, Keyword
from app.models.note import Note,NoteImage
from app.models.task import CrawlTask,TaskLog
from app.services.crawler import AuthenticationRequired
from app.services.extraction import extract_activities
from app.services.dedup import create_duplicate_candidates
from app.services.archive import archive_task_folder,archive_task_result
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
        requested_cities=[task.params['city']] if task.params.get('city') else task.params.get('cities',[])
        city_query=select(City).where(City.enabled.is_(True))
        if requested_cities: city_query=city_query.where(City.code.in_(requested_cities))
        cities=list(db.scalars(city_query.order_by(City.id)).all())
        if cities:
            for city in cities:
                configured_keywords=list(db.scalars(select(Keyword.word).where(Keyword.city_code==city.code,Keyword.enabled.is_(True)).order_by(Keyword.id)).all())
                keywords=task.params.get('keywords') or configured_keywords
                recent_filter=task.params.get('recent_filter') or city.recent_filter
                for keyword in keywords: results.extend((city.code,x) for x in adapter.search_recent(f'{city.name} {keyword}',recent_filter))
                blogger_ids=task.params.get('blogger_ids',[])
                if blogger_ids:
                    bloggers=list(db.scalars(select(Blogger).where(Blogger.id.in_(blogger_ids),Blogger.city_code==city.code,Blogger.enabled.is_(True))).all())
                    for blogger in bloggers: results.extend((city.code,x) for x in adapter.blogger_notes(blogger.profile_url))
        else:
            for city_code in requested_cities:
                for keyword in task.params.get('keywords',[]): results.extend((city_code,x) for x in adapter.search_recent(f'{city_code} {keyword}','一周内'))
        task.status='DOWNLOADING'; task.total_notes=len(results); db.commit()
        for city,item in results:
            if db.scalar(select(Note).where(Note.source_url==item['url'])): continue
            detail=adapter.note(item['url']); note=Note(task_id=task.id,platform_note_id=item['url'].split('/')[-1].split('?')[0],title=item.get('title',''),content=detail.get('content',''),source_url=item['url'],city_code=city,status='DOWNLOADED',raw_data=detail); db.add(note); db.flush()
            started_at=task.started_at or datetime.now(timezone.utc); folder=archive_task_folder(settings.archive_dir,started_at,task.id); download_dir=folder/'.downloads'/note.platform_note_id
            images=adapter.download(item['url'],download_dir)
            ocr_texts=[]
            ocr=OCRService(PaddleOCREngine(settings),settings.ocr_min_confidence) if settings.ocr_enabled else None
            image_rows=[]
            for index,image in enumerate(images,1):
                result=ocr.process(image) if ocr else {'status':'disabled','text':'','error':''}
                image_row=NoteImage(note_id=note.id,storage_key='',ocr_text=result['text'],ocr_status=result['status'],ocr_error=result['error']); db.add(image_row); image_rows.append((image,image_row))
                if result['text']: ocr_texts.append(f"[IMAGE {index}]\n{result['text']}")
            note.status='OCR_DONE' if ocr else 'DOWNLOADED'
            combined=f"标题：{note.title}\n正文：{note.content}\n"+'\n'.join(ocr_texts); client=MiniMaxClient(settings); extracted=extract_activities(combined,datetime.now(),client.extract_many if settings.minimax_api_key else None)
            created=[]
            for fields in extracted:
                activity=Activity(note_id=note.id,name=fields.get('name') or note.title,city_code=city,start_time=datetime.fromisoformat(fields['start_time']) if fields.get('start_time') else datetime.now(timezone.utc),end_time=datetime.fromisoformat(fields['end_time']) if fields.get('end_time') else None,location=fields.get('location') or '',price=fields.get('price') or '',type=fields.get('type') or '其他',source_url=note.source_url,source_image_indexes=fields.get('source_image_indexes') or [],summary=fields.get('summary') or note.content[:300],status=fields['status'],confidence=float(fields.get('confidence') or 0)); db.add(activity); db.flush(); create_duplicate_candidates(db,activity); created.append(activity)
            task_note_ids=select(Note.id).where(Note.task_id==task.id); task_activities=list(db.scalars(select(Activity).where(Activity.note_id.in_(task_note_ids)).order_by(Activity.id)).all())
            archive_task_result(settings.archive_dir,started_at,task.id,note,image_rows,task_activities)
            shutil.rmtree(folder/'.downloads',ignore_errors=True)
            task.success_notes+=1; db.commit()
        task.status='COMPLETED'; task.finished_at=datetime.now(timezone.utc); db.commit(); log(db,task.id,'INFO','completed')
    except AuthenticationRequired as exc:
        task.status='PAUSED'; task.error_message=str(exc); db.commit(); log(db,task.id,'ERROR',str(exc))
    except Exception as exc:
        task.status='FAILED'; task.error_message=str(exc); db.commit(); log(db,task.id,'ERROR',str(exc)); raise self.retry(exc=exc,countdown=300)
    finally: db.close()
