import json
import re
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus
from app.core.config import Settings
from app.services.crawler import AuthenticationRequired, OpenCLIError

class OpenCLIAdapter:
    def __init__(self, settings:Settings, session:str='xhs-crawler') -> None: self.settings=settings; self.session=session
    def run(self,args:list[str]) -> Any:
        result=subprocess.run(['opencli',*args],capture_output=True,text=True,timeout=120)
        output=result.stdout.strip()
        if result.returncode==77: raise AuthenticationRequired('请在 Chrome 登录小红书后重试')
        if result.returncode: raise OpenCLIError(result.stderr.strip() or output)
        try: return json.loads(output)
        except json.JSONDecodeError: return output
    def check_login(self): return self.run(['xiaohongshu','whoami','-f','json','--window','background'])
    @staticmethod
    def normalize_note(value:Any)->dict[str,Any]:
        if isinstance(value,dict): return value
        if isinstance(value,list) and all(isinstance(row,dict) and 'field' in row for row in value):
            return {str(row['field']):row.get('value') for row in value}
        raise OpenCLIError(f'unexpected note response: {type(value).__name__}')
    def _state(self)->str: return str(self.run(['browser',self.session,'state']))
    def _click_text_ref(self,state:str,text:str) -> None:
        match=re.search(rf'\[(\d+)\]<(?:div|span|button)[^>]*>[^\n]*{re.escape(text)}',state)
        if not match: raise OpenCLIError(f'filter option not found: {text}')
        self.run(['browser',self.session,'click',match.group(1)])
    def search_recent(self,query:str)->list[dict[str,Any]]:
        self.check_login(); url=f'https://www.xiaohongshu.com/search_result?keyword={quote_plus(query)}'
        self.run(['browser',self.session,'open',url,'--window','background']); self.run(['browser',self.session,'wait','time','2'])
        state=self._state(); self._click_text_ref(state,'筛选'); self.run(['browser',self.session,'wait','time','1']); state=self._state(); self._click_text_ref(state,'最新'); self._click_text_ref(state,'一周内'); self.run(['browser',self.session,'wait','time','2'])
        script=r"""(() => Array.from(document.querySelectorAll('section')).map(s => { const links=[...s.querySelectorAll('a[href*="/search_result/"]')]; const title=s.querySelector('a[href*="/search_result/"] span')?.textContent?.trim(); const time=[...s.querySelectorAll('div')].map(x=>x.textContent?.trim()).find(x=>/^(\d+分钟前|\d+小时前|\d+天前|\d{2}-\d{2})$/.test(x||'')); return title&&links[0]?{title,url:new URL(links[0].getAttribute('href'),location.origin).href,published_text:time||''}:null }).filter(Boolean))()"""
        previous=0; stagnant=0; items=[]
        for _ in range(self.settings.xhs_search_scroll_max_rounds+1):
            items=self.run(['browser',self.session,'eval',script]) or []
            if len(items)>=self.settings.xhs_search_target_count: break
            stagnant=stagnant+1 if len(items)<=previous else 0
            if stagnant>=self.settings.xhs_scroll_stagnant_rounds: break
            previous=len(items); self.run(['browser',self.session,'scroll','down','--amount',str(self.settings.xhs_scroll_pixels)]); self.run(['browser',self.session,'wait','time','1'])
        self.run(['browser',self.session,'close']); return items[:self.settings.xhs_search_target_count]
    def note(self,url:str)->dict[str,Any]:
        self.check_login()
        self.run(['browser',self.session,'open',url,'--window','background']); self.run(['browser',self.session,'wait','time','2'])
        previous=0; stagnant=0
        for _ in range(self.settings.xhs_detail_scroll_max_rounds):
            height=int(self.run(['browser',self.session,'eval','document.documentElement.scrollHeight']) or 0)
            stagnant=stagnant+1 if height<=previous else 0
            if stagnant>=self.settings.xhs_scroll_stagnant_rounds: break
            previous=height
            self.run(['browser',self.session,'scroll','down','--amount',str(self.settings.xhs_scroll_pixels)])
            self.run(['browser',self.session,'wait','time','1'])
        self.run(['browser',self.session,'close'])
        return self.normalize_note(self.run(['xiaohongshu','note',url,'-f','json','--window','background']))
    def download(self,url:str,output_dir:Path)->list[Path]:
        self.check_login(); output_dir.mkdir(parents=True,exist_ok=True)
        before={path.resolve() for path in output_dir.rglob('*') if path.is_file()}
        self.run(['xiaohongshu','download',url,'--output',str(output_dir),'-f','json','--window','background'])
        suffixes={'.jpg','.jpeg','.png','.webp','.bmp'}
        return sorted(path for path in output_dir.rglob('*') if path.is_file() and path.resolve() not in before and path.suffix.lower() in suffixes)
