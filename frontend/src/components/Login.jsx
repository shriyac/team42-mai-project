import React,{useRef,useState} from 'react';
import {ArrowRight,ArrowLeft,Building2,Home,ShieldCheck,Sparkles} from 'lucide-react';
import {Logo,Button,Badge,ErrorNotice,PropertyArt} from './ui.jsx';
export default function Login({gateway,onLogin,developerAccess}){
 const [role,setRole]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState(null);
 const submitting=useRef(false);
 function chooseRole(value){setRole(value);setError(null)}
 async function submit(e){
  e.preventDefault();if(submitting.current)return;submitting.current=true;setBusy(true);setError(null);
  try{
   if(gateway.mode==='mock')throw new Error('Account sign-in requires the local API. Start Laga with npm run dev:local.');
   const form=new FormData(e.currentTarget);
   const session=await gateway.login({email:form.get('email').trim(),password:form.get('password')});
   onLogin(session.user);
  }catch(error){setError(error)}finally{submitting.current=false;setBusy(false)}
 }
 return <main className="login-page"><section className="login-story"><div className="login-brand"><Logo/><span className="brand-meaning">Lease Agreement Guard Agent</span></div><div className="login-story-content"><Badge tone="lavender"><Sparkles size={13}/>A little clarity changes everything</Badge><h1>Good leases.<br/>Better understanding.</h1><p>Your home, your agreement, your peace of mind. Bring everything into focus with Laga.</p><PropertyArt large/><div className="login-values"><span><ShieldCheck size={17}/>Answers with sources</span><span><Home size={17}/>People before paperwork</span></div></div><footer>Clearer conversations. Stronger relationships.</footer></section><section className="login-entry"><div className="login-developer-access">{developerAccess}</div><div className="login-card"><span className="eyebrow">WELCOME TO LAGA</span>{!role?<><h2>Find your place.</h2><p>Choose how you use Laga to sign in.</p><div className="login-options" role="group" aria-label="Choose login type">{[['tenant','Tenant login',Home],['landlord','Landlord login',Building2]].map(([value,label,Icon])=><button type="button" className="login-option" key={value} onClick={()=>chooseRole(value)}><span className="login-option-icon"><Icon size={30} aria-hidden="true"/></span><strong>{label}</strong><small>{value==='tenant'?'Your home and lease':'Your rental portfolio'}</small><ArrowRight size={18} aria-hidden="true"/></button>)}</div></>:<><button type="button" className="text-button login-back" onClick={()=>chooseRole(null)} disabled={busy}><ArrowLeft size={15} aria-hidden="true"/>Back to login options</button><h2>{role==='tenant'?'Tenant login':'Landlord login'}</h2><p>Sign in with your email address and password.</p><form key={role} onSubmit={submit}><label htmlFor="login-email">Email address<input id="login-email" type="email" name="email" autoComplete="username" autoFocus required disabled={busy}/></label><label htmlFor="login-password">Password<input id="login-password" name="password" type="password" autoComplete="current-password" required disabled={busy}/></label><ErrorNotice error={error}/><Button type="submit" variant="primary" className="login-submit" disabled={busy}>{busy?'Signing in...':'Sign in'}<ArrowRight size={17} aria-hidden="true"/></Button></form><div className="login-trust"><ShieldCheck size={15} aria-hidden="true"/><span>Your access is determined by your account permissions.</span></div></>}</div><footer>Built for the people on both sides of the lease.</footer></section></main>
}
