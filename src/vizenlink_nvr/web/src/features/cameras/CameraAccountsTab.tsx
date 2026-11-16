import { NativeSelect } from "@/components/ui/native-select";
import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import { useCurrentUser } from "@/lib/queries";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { InlineError } from "@/components/InlineError";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";

interface AccountState { accounts: Array<{username:string; role:string}>; roles:string[]; max_users:number; current_username:string }
export function CameraAccountsTab({ serial, cameraName }: { serial:string; cameraName:string }) {
  const owner = useCurrentUser()?.role === "owner";
  const base = `/api/v1/cameras/${encodeURIComponent(serial)}/accounts`;
  const state = useQuery({queryKey:["cameraAccounts", serial], queryFn:()=>apiFetch<AccountState>(base), enabled:owner, retry:false});
  const [action, setAction] = useState("create");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("");
  const [review, setReview] = useState(false);
  const [confirmation, setConfirmation] = useState("");
  const mutation = useMutation({gcTime:0, mutationFn:()=>apiFetch(base,{method:"POST",body:{action,username,role:action === "role" || action === "create" ? role : undefined,password:action === "password" || action === "create" ? password : undefined,confirmation:serial}}),onSuccess:()=>{setPassword("");setReview(false);void state.refetch();},onError:()=>setReview(false)});
  if (!owner) return <p className="rounded-xl border border-border bg-card p-6 text-sm">Only the recorder owner can manage accounts stored on the camera.</p>;
  if (state.isPending) return <p className="p-6 text-sm">Reading accounts from the camera…</p>;
  if (state.error) return <InlineError message={state.error.message} actionLabel="Reload camera accounts" onAction={()=>void state.refetch()} />;
  const data = state.data!;
  const editable = data.accounts.filter(a=>a.role !== "Administrator" && a.username !== data.current_username);
  return <div className="flex flex-col gap-6"><div><h2 className="text-xl font-semibold">Camera accounts</h2><p className="mt-2 text-sm text-muted-foreground">These accounts sign in directly to this camera. Recorder users are managed in Settings. The camera connection must have Administrator access.</p></div>
    <section className="rounded-xl border border-border bg-card p-6"><h3 className="mb-4 font-semibold">{data.accounts.length} of {data.max_users} camera accounts</h3><div className="grid gap-2">{data.accounts.map(account=><div key={account.username} className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-background p-4"><span className="text-sm font-semibold">{account.username}{account.username===data.current_username ? " · Recorder connection" : ""}</span><span className="text-sm text-muted-foreground">{account.role}</span></div>)}</div></section>
    <form className="flex flex-col gap-4 rounded-xl border border-border bg-card p-6" onSubmit={e=>{e.preventDefault();setConfirmation("");setReview(true);}}><h3 className="font-semibold">Manage camera access</h3><div className="grid gap-4 sm:grid-cols-2"><label className="vms-field">Action<NativeSelect value={action} onChange={e=>{setAction(e.target.value);setUsername("");setPassword("");}}><option value="create">Create camera account</option><option value="role">Change account role</option><option value="password">Reset account password</option><option value="delete">Delete camera account</option></NativeSelect></label>
      <label className="vms-field">Camera username{action === "create" ? <Input required minLength={1} maxLength={32} value={username} onChange={e=>setUsername(e.target.value)} autoComplete="off"/> : <NativeSelect required value={username} onChange={e=>setUsername(e.target.value)}><option value="">Choose account…</option>{editable.map(a=><option key={a.username}>{a.username}</option>)}</NativeSelect>}</label>
      {(action === "create" || action === "role") && <label className="vms-field">Camera role<NativeSelect required value={role} onChange={e=>setRole(e.target.value)}><option value="">Choose role…</option>{data.roles.map(r=><option key={r}>{r}</option>)}</NativeSelect></label>}
      {(action === "create" || action === "password") && <label className="vms-field">New camera password<Input required type="password" minLength={1} maxLength={32} value={password} onChange={e=>setPassword(e.target.value)} autoComplete="new-password"/></label>}</div>
      <p className="text-xs text-muted-foreground">The Administrator and recorder connection accounts are protected. Use Details to update the recorder's camera password. The camera enforces its own password rules.</p><Button type="submit" className="self-start" disabled={mutation.isPending || action === "create" && data.accounts.length >= data.max_users}>Review account change</Button>
      {mutation.error && <p role="alert" className="text-sm text-critical">{mutation.error.message}</p>}{mutation.isSuccess && <p role="status" className="text-sm text-success">Camera confirmed the account change.</p>}
    </form>
    <Dialog open={review} onOpenChange={setReview}><DialogContent><DialogHeader><DialogTitle>Confirm camera account change</DialogTitle><DialogDescription>{action === "delete" ? "Deleting this account immediately ends its camera sessions and cannot be undone." : "This changes who can sign in directly to the camera or the access they have."}</DialogDescription></DialogHeader><p className="text-sm">Camera: {cameraName} · Account: {username} · Action: {action}{action === "create" || action === "role" ? ` · Role: ${role}` : ""}</p><label className="vms-field">Type the camera name to confirm<Input value={confirmation} onChange={e=>setConfirmation(e.target.value)} autoComplete="off"/></label><Button disabled={confirmation!==cameraName || mutation.isPending} onClick={()=>mutation.mutate()}>Apply camera account change</Button></DialogContent></Dialog>
  </div>;
}
