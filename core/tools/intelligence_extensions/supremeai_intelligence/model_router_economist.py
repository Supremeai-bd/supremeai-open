from dataclasses import dataclass


@dataclass
class ModelStats:
    provider:str; model:str; success_rate:float=.95; avg_latency_ms:float=500; cost_per_1k_tokens:float=.001; capacity_score:float=1.; quality_by_domain:dict|None=None
    def quality(self,d):return float((self.quality_by_domain or {}).get(d,self.success_rate))
@dataclass
class RouteDecision:
    models:list[tuple[str,str]]; tier:str; expected_cost:float; expected_latency_ms:float; rationale:list[str]
class ModelRouterEconomist:
    def __init__(self,models):
        if not models:raise ValueError('no models')
        self.models=models
    def choose(self,domain='general',complexity=.5,risk=.5,budget=None,expected_output_tokens=1200,require_consensus=None):
        consensus=(risk>=.7 or complexity>=.8) if require_consensus is None else require_consensus
        ranked=sorted(self.models,key=lambda m:.55*m.quality(domain)+.2*m.capacity_score-.15*(m.avg_latency_ms/2000)-.1*(m.cost_per_1k_tokens/.01),reverse=True)
        n=3 if consensus else (2 if complexity>=.6 else 1); sel=ranked[:min(n,len(ranked))]
        cost=sum(m.cost_per_1k_tokens*expected_output_tokens/1000 for m in sel)
        if budget is not None and cost>budget:sel=[min(ranked,key=lambda m:m.cost_per_1k_tokens)]; cost=sel[0].cost_per_1k_tokens*expected_output_tokens/1000
        return RouteDecision([(m.provider,m.model) for m in sel],'ensemble' if len(sel)>1 else 'fast',cost,max(m.avg_latency_ms for m in sel),[f'complexity={complexity:.2f}',f'risk={risk:.2f}'])
