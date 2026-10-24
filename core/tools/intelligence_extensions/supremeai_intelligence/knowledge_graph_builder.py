import hashlib
import json
from dataclasses import dataclass, field


@dataclass(frozen=True)
class GraphNode: node_id:str; kind:str; label:str; metadata:dict=field(default_factory=dict)
@dataclass(frozen=True)
class GraphEdge: source:str; relation:str; target:str; weight:float=1.
@dataclass
class KnowledgeGraph: nodes:dict[str,GraphNode]=field(default_factory=dict); edges:list[GraphEdge]=field(default_factory=list)
class KnowledgeGraphBuilder:
    MAP={'dependencies':'depends_on','causes':'causes','effects':'affects','solutions':'solves','failures':'fails_as','concepts':'relates_to'}
    def build(self,arts):
        g=KnowledgeGraph()
        for a in arts:
            aid=str(a.get('artifact_id') or a.get('id') or hashlib.sha256(json.dumps(a,sort_keys=True).encode()).hexdigest()[:20]); g.nodes[aid]=GraphNode(aid,'knowledge',str(a.get('title') or a.get('claim') or aid),{'domain':a.get('domain','general')})
            for key,rel in self.MAP.items():
                vals=a.get(key,[]); vals=[vals] if isinstance(vals,str) else vals
                for v in vals:
                    label=str(v).strip(); nid=f'{key}:{hashlib.sha256(label.lower().encode()).hexdigest()[:20]}'; g.nodes.setdefault(nid,GraphNode(nid,key.removesuffix('s'),label)); g.edges.append(GraphEdge(aid,rel,nid))
        return g
