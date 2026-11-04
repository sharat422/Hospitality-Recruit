import { useAuth } from '@/lib/AuthContext'
import { supabase } from '@/lib/supabase'
import { ShieldCheck,Smartphone } from 'lucide-react'
import { useState } from 'react'
import { Navigate,useNavigate } from 'react-router-dom'

const copy = {
  en: { title:'Employee login', sub:'Use the mobile number registered with HR', phone:'Mobile number', send:'Send OTP', otp:'6-digit OTP', verify:'Verify and continue', note:'Standard SMS charges may apply.' },
  hi: { title:'कर्मचारी लॉगिन', sub:'HR में दर्ज मोबाइल नंबर का उपयोग करें', phone:'मोबाइल नंबर', send:'OTP भेजें', otp:'6 अंकों का OTP', verify:'सत्यापित करें', note:'सामान्य SMS शुल्क लागू हो सकता है।' },
}

export default function EmployeeLogin(){
 const {isAuthenticated}=useAuth();const navigate=useNavigate();const [lang,setLang]=useState<'en'|'hi'>('en')
 const [phone,setPhone]=useState('+91'),[otp,setOtp]=useState(''),[sent,setSent]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('')
 if(isAuthenticated)return <Navigate to="/employee-app" replace/>
 const normalized=()=>phone.replace(/[\s-]/g,'').replace(/^91(?=\d{10}$)/,'+91').replace(/^(?=\d{10}$)/,'+91')
 const send=async()=>{setBusy(true);setError('');const value=normalized();if(!/^\+91[6-9]\d{9}$/.test(value)){setError(lang==='hi'?'सही भारतीय मोबाइल नंबर दर्ज करें।':'Enter a valid Indian mobile number.');setBusy(false);return}const {error}=await supabase.auth.signInWithOtp({phone:value,options:{shouldCreateUser:false}});if(error)setError(error.message);else{setPhone(value);setSent(true)}setBusy(false)}
 const verify=async()=>{setBusy(true);setError('');const {error}=await supabase.auth.verifyOtp({phone:normalized(),token:otp,type:'sms'});if(error)setError(error.message);else navigate('/employee-app',{replace:true});setBusy(false)}
 const t=copy[lang]
 return <main className="min-h-screen bg-slate-50 px-4 py-8 flex items-center justify-center"><section className="w-full max-w-sm bg-white border border-slate-200 rounded-lg p-5 shadow-sm">
  <div className="flex justify-end"><div className="flex border rounded-md p-1"><button onClick={()=>setLang('en')} className={`min-h-10 px-3 text-sm ${lang==='en'?'bg-slate-900 text-white rounded':''}`}>English</button><button onClick={()=>setLang('hi')} className={`min-h-10 px-3 text-sm ${lang==='hi'?'bg-slate-900 text-white rounded':''}`}>हिन्दी</button></div></div>
  <div className="my-6"><div className="w-11 h-11 bg-emerald-100 text-emerald-700 flex items-center justify-center rounded-md"><Smartphone/></div><h1 className="mt-4 text-2xl font-semibold text-slate-900">{t.title}</h1><p className="mt-1 text-sm text-slate-600">{t.sub}</p></div>
  {!sent?<label className="block text-sm font-medium text-slate-700">{t.phone}<input inputMode="tel" autoComplete="tel" value={phone} onChange={e=>setPhone(e.target.value)} className="mt-2 min-h-12 w-full rounded-md border px-3 text-lg"/></label>:<label className="block text-sm font-medium text-slate-700">{t.otp}<input inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={otp} onChange={e=>setOtp(e.target.value.replace(/\D/g,''))} className="mt-2 min-h-12 w-full rounded-md border px-3 text-center text-2xl tracking-[.35em]"/></label>}
  {error&&<div role="alert" className="mt-3 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}
  <button disabled={busy||(sent?otp.length!==6:false)} onClick={sent?verify:send} className="mt-5 min-h-12 w-full rounded-md bg-emerald-600 px-4 font-medium text-white disabled:opacity-50">{busy?'…':sent?t.verify:t.send}</button>
  {sent&&<button onClick={()=>setSent(false)} className="min-h-11 w-full text-sm text-slate-600">{lang==='hi'?'नंबर बदलें':'Change number'}</button>}
  <p className="mt-4 flex gap-2 text-xs text-slate-500"><ShieldCheck size={16}/>{t.note}</p>
 </section></main>
}
