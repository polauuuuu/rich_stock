type JobState={id:string;kind:string;state:string}
export function completedDownloads(jobs:JobState[],seen:Map<string,string>):string[]{
  const completed:string[]=[]
  for(const job of jobs){
    const previous=seen.get(job.id)
    if(job.kind==='download'&&job.state==='completed'&&previous&&['queued','running','cancelling'].includes(previous)) completed.push(job.id)
    seen.set(job.id,job.state)
  }
  return completed
}
