import React from 'react';
import {ArrowUpRight,Code2} from 'lucide-react';

export default function DeveloperAccess({enabled,onToggle}){
 return <div className="developer-access"><button type="button" className="developer-toggle" role="switch" aria-checked={enabled} onClick={()=>onToggle(!enabled)}><Code2 size={15}/><span>Developer Tools</span><span className={'developer-switch '+(enabled?'enabled':'')} aria-hidden="true"><i/></span></button><span className="developer-docs-slot"><a className="developer-docs-link" hidden={!enabled} href="/api-docs/" target="_blank" rel="noopener noreferrer">API Docs<ArrowUpRight size={14}/><span className="sr-only"> (opens in a new tab)</span></a></span></div>
}
