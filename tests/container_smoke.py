"""Run after docker build -t clinical-compass:demo . Uses an ephemeral container."""

import subprocess, time

container = subprocess.check_output(
    ["docker", "run", "--rm", "--detach", "clinical-compass:demo"], text=True
).strip()
try:
    for _ in range(40):
        result = subprocess.run(
            [
                "docker",
                "exec",
                container,
                "python",
                "-c",
                "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=2)",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            break
        time.sleep(0.25)
    else:
        raise RuntimeError("Container did not become ready")
    code = """
import http.cookiejar,json,os,urllib.request,urllib.error
assert os.getuid()!=0
client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
def request(path,data=None,csrf=''):
 req=urllib.request.Request('http://127.0.0.1:8000'+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json','X-CSRF-Token':csrf})
 with client.open(req,timeout=5) as response:return json.load(response)
assert request('/api/health')['version']=='synthetic-3.0'
try:request('/api/patients');raise AssertionError('Anonymous access')
except urllib.error.HTTPError as error:assert error.code==401
patient=request('/api/auth/login',{'username':'patient-a','password':'compass-demo'})
report={'mood':6,'anxiety':4,'adherence':'Да','adverse_effects':'','note':'Container smoke: synthetic','safety_signal':False}
request('/api/patients/2/reports',report,patient['csrf'])
request('/api/auth/logout',{},patient['csrf'])
doctor=request('/api/auth/login',{'username':'doctor','password':'compass-demo'})
assert [p['id'] for p in request('/api/patients')]==[2,3]
assert request('/api/patients/2')['reports'][0]['note']=='Container smoke: synthetic'
assert request('/api/notifications')['unread']>0
assert request('/api/integrations')['worker_last_seen']
assert len(request('/api/appointments'))==2
assert len(request('/api/surveys/templates'))>=3
assert request('/api/patients/2')['care']['prescriptions']
request('/api/auth/logout',{},doctor['csrf'])
print('PASS: container runs as non-root; health, sessions, role checks, report persistence, care workflows and background scheduler')
"""
    result = subprocess.run(
        ["docker", "exec", "-i", container, "python", "-"],
        input=code,
        text=True,
        capture_output=True,
    )
    print(result.stdout)
    if result.returncode:
        raise RuntimeError(result.stderr)
finally:
    subprocess.run(["docker", "stop", container], stdout=subprocess.DEVNULL, check=True)
