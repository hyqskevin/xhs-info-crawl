import { http } from './http'
export const api={
  login:(username:string,password:string)=>http.post('/auth/login',{username,password}),
  dashboard:()=>http.get('/dashboard/summary'),
  activities:(params={})=>http.get('/activities',{params}),activity:(id:number)=>http.get(`/activities/${id}`),updateActivity:(id:number,data:object)=>http.put(`/activities/${id}`,data),deleteActivity:(id:number)=>http.delete(`/activities/${id}`),deleteActivities:(ids:number[])=>http.delete('/activities/batch',{data:{ids}}),
  tasks:()=>http.get('/tasks'),createTask:(data:object)=>http.post('/tasks/crawl',data),logs:(id:number)=>http.get(`/tasks/${id}/logs`),
  duplicates:()=>http.get('/duplicates'),merge:(id:number,keep='a')=>http.post(`/duplicates/${id}/merge`,{keep}),ignore:(id:number)=>http.post(`/duplicates/${id}/ignore`),
  reports:()=>http.get('/reports'),generateReport:(data:object)=>http.post('/reports/generate',data),report:(id:number)=>http.get(`/reports/${id}`),downloadReport:(id:number,format:'md'|'xlsx')=>http.get(`/reports/${id}/download`,{params:{format},responseType:'blob'}),
  settings:(kind:string)=>http.get(`/settings/${kind}`),createSetting:(kind:string,data:object)=>http.post(`/settings/${kind}`,data),updateSetting:(kind:string,id:number,data:object)=>http.put(`/settings/${kind}/${id}`,data),deleteSetting:(kind:string,id:number)=>http.delete(`/settings/${kind}/${id}`),testOpenCLI:()=>http.post('/settings/opencli/test',undefined,{skipAuthRedirect:true} as any),
}
