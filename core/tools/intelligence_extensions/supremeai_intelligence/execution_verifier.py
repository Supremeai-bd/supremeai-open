import ast
import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

Sandbox=Callable[[str,str],Awaitable[dict]]
@dataclass
class ExecutionReport:
    passed:bool; static_checks:list[dict]=field(default_factory=list); tests:list[dict]=field(default_factory=list); benchmarks:list[dict]=field(default_factory=list); violations:list[str]=field(default_factory=list)
class ExecutionVerifier:
    def __init__(self,sandbox_runner:Sandbox|None=None,timeout_s=30,deny_imports=None): self.sandbox=sandbox_runner; self.timeout=timeout_s; self.deny=set(deny_imports or {'subprocess','ctypes','pickle','marshal','pty'})
    async def verify_python(self,code,test_code=None,benchmark_code=None):
        checks=[]; violations=[]
        try:t=ast.parse(code)
        except SyntaxError as e:return ExecutionReport(False,[{'name':'ast','passed':False,'error':str(e)}],violations=['syntax_error'])
        for n in ast.walk(t):
            if isinstance(n,ast.Import):
                for a in n.names:
                    if a.name.split('.')[0] in self.deny:violations.append(a.name.split('.')[0])
            elif isinstance(n,ast.ImportFrom) and n.module and n.module.split('.')[0] in self.deny: violations.append(n.module.split('.')[0])
        checks.append({'name':'ast','passed':not violations,'violations':violations})
        results=[]; benches=[]
        for kind,snip,out in [('test',test_code,results),('benchmark',benchmark_code,benches)]:
            if snip and self.sandbox:
                try: out.append(await asyncio.wait_for(self.sandbox(snip,kind),self.timeout))
                except Exception as e: out.append({'passed':False,'error':str(e)})
        passed=not violations and all(x.get('passed',True) for x in checks+results+benches)
        return ExecutionReport(passed,checks,results,benches,violations)
