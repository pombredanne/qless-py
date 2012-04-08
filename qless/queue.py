#! /usr/bin/env python

import time
import uuid
from job import Job
import simplejson as json

# The Queue class
class Queue(object):
    def __init__(self, name, client, worker):
        self.name    = name
        self.client  = client
        self.worker  = worker
        self._hb     = 60
    
    def put(self, data, priority=None, tags=None, delay=None, retries=None):
        # '''Put(1, queue, id, data, now, [priority, [tags, [delay, [retries]]]])
        # -----------------------------------------------------------------------
        # Either create a new job in the provided queue with the provided attributes,
        # or move that job into that queue. If the job is being serviced by a worker,
        # subsequent attempts by that worker to either `heartbeat` or `complete` the
        # job should fail and return `false`.
        #     
        # The `priority` argument should be negative to be run sooner rather than 
        # later, and positive if it's less important. The `tags` argument should be
        # a JSON array of the tags associated with the instance and the `valid after`
        # argument should be in how many seconds the instance should be considered 
        # actionable.'''
        return self.client._put([self.name], [
            uuid.uuid1().hex,
            json.dumps(data),
            time.time(),
            priority or 0,
            json.dumps(tags or []),
            delay or 0,
            retries or 5
        ])
    
    def pop(self, count=None):
        '''Pop(1, queue, worker, count, now, expiration)
        ---------------------------------------------
        Passing in the queue from which to pull items, the current time, when the locks
        for these returned items should expire, and the number of items to be popped
        off.'''
        results = [Job(self.client, **json.loads(j)) for j in self.client._pop([self.name], [self.worker, count or 1, time.time(), time.time() + self._hb])]
        if count == None:
            return (len(results) and results[0]) or None
        return results
    
    def peek(self, count=None):
        '''Peek(1, queue, count, now)
        --------------------------
        Similar to the `Pop` command, except that it merely peeks at the next items
        in the queue.'''
        results = [Job(self.client, **json.loads(r)) for r in self.client._peek([self.name], [count or 1, time.time()])]
        if count == None:
            return (len(results) and results[0]) or None
        return results
    
    def fail(self, job, t, message):
        '''Fail(0, id, worker, type, message, now, [data])
        -----------------------------------------------
        Mark the particular job as failed, with the provided type, and a more specific
        message. By `type`, we mean some phrase that might be one of several categorical
        modes of failure. The `message` is something more job-specific, like perhaps
        a traceback.
        
        This method should __not__ be used to note that a job has been dropped or has 
        failed in a transient way. This method __should__ be used to note that a job has
        something really wrong with it that must be remedied.
        
        The motivation behind the `type` is so that similar errors can be grouped together.
        Optionally, updated data can be provided for the job. A job in any state can be
        marked as failed. If it has been given to a worker as a job, then its subsequent
        requests to heartbeat or complete that job will fail. Failed jobs are kept until
        they are canceled or completed. __Returns__ the id of the failed job if successful,
        or `False` on failure.'''
        return self.client._fail([], [job.id, self.worker, t, message, time.time(), json.dumps(job.data)]) or False
    
    def heartbeat(self, job):
        '''Heartbeat(0, id, worker, expiration, [data])
        -------------------------------------------
        Renew the heartbeat, if possible, and optionally update the job's user data.'''
        return float(self.client._heartbeat([], [job.id, self.worker, time.time() + self._hb, json.dumps(job.data)]) or 0)
    
    def complete(self, job, next=None, delay=None):
        '''Complete(0, id, worker, queue, now, [data, [next, [delay]]])
        -----------------------------------------------
        Complete a job and optionally put it in another queue, either scheduled or to
        be considered waiting immediately.'''
        if next:
            return self.client._complete([], [job.id, self.worker, self.name,
                time.time(), json.dumps(job.data), next, delay or 0]) or False
        else:
            return self.client._complete([], [job.id, self.worker, self.name,
                time.time(), json.dumps(job.data)]) or False
    
    def stats(self, date=None):
        '''Stats(0, queue, date)
        ---------------------
        Return the current statistics for a given queue on a given date. The results 
        are returned are a JSON blob:
        
            {
                'total'    : ...,
                'mean'     : ...,
                'variance' : ...,
                'histogram': [
                    ...
                ]
            }
        
        The histogram's data points are at the second resolution for the first minute,
        the minute resolution for the first hour, the 15-minute resolution for the first
        day, the hour resolution for the first 3 days, and then at the day resolution
        from there on out. The `histogram` key is a list of those values.'''
        return json.loads(self.client._stats([], [self.name, date or time.time()]))
    
    def __len__(self):
        with self.client.redis.pipeline() as p:
            o = p.zcard('ql:q:' + self.name + '-locks')
            o = p.zcard('ql:q:' + self.name + '-work')
            o = p.zcard('ql:q:' + self.name + '-scheduled')
            return sum(p.execute())