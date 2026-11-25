/**
 * Wolo-owned compatibility adapter, not an HD signer or Comet verifier.
 * Input MUST be freshly written by the genuine Go native test in this job.
 * Untouched HD source validates economics and disposable SQL accounting.
 * The held NativePgIngest code and all production switches remain unused.
 */
import assert from "node:assert/strict";
import {createHash} from "node:crypto";
import {readFileSync,statSync} from "node:fs";
import {createRequire} from "node:module";
import path from "node:path";
import {inspectEpochV3TicketFunding} from "../tests/fixtures/hd940-source/lib/warSatchelEpochV3TicketFunding.ts";
import {planNewEpochMarketSettlement} from "../tests/fixtures/hd940-source/lib/warSatchelNewEpochFinancialContracts.ts";

type J=Record<string,any>;
const base=new URL("../tests/fixtures/hd940-source/",import.meta.url);
const PROTOCOL="aoe2war/escrow-epoch/v3", HD="b7e07645e057340de051c5ffa78001ebc939191e";
const sha=(v:string|Buffer)=>createHash("sha256").update(v).digest("hex");
const load=(p:string)=>JSON.parse(readFileSync(new URL(p,base),"utf8"));
const manifest=load("manifest.json");
assert.equal(manifest.commit,HD);
for(const f of manifest.files){
 const b=readFileSync(new URL(f.path,base));
 assert.equal(sha(b),f.sha256,f.path+": SHA256");
 const blob=createHash("sha1").update(Buffer.from("blob "+b.length+"\0")).update(b).digest("hex");
 assert.equal(blob,f.git_blob_sha,f.path+": Git blob");
}
const mismatch=load("known-mismatches.json");
assert.equal(mismatch.hd_commit,HD);
assert.equal(mismatch.financial_activation_authorized,false);

const filename=process.argv.find(x=>x.startsWith("--golden="))?.slice(9)||process.env.WOLO_EPOCH_GOLDEN_OUT;
assert.ok(filename,"Set WOLO_EPOCH_GOLDEN_OUT to fresh Go native golden");
assert.ok(statSync(filename!).size<=16*1024*1024,"Sanitized golden exceeds 16 MiB bound");
const rawGolden=readFileSync(filename!);
const g=JSON.parse(rawGolden.toString("utf8"));
assert.equal(g.schema_version,1);
assert.equal(g.fixture_only,true);
assert.equal(g.mainnet_authority,false);
assert.equal(g.production_custody_available,false);
const p=g.policy;
assert.ok(p.vault&&p.escrow&&p.vault!==p.escrow);
assert.equal(g.source_sha,p.source_commit);
assert.equal(g.native_test_binary_sha256,p.binary_sha256);
assert.match(g.source_sha,/^[a-f0-9]{40}$/);assert.match(g.native_test_binary_sha256,/^[a-f0-9]{64}$/);
assert.match(g.compiler,/^go1\.[0-9]+/);
const expectedSource=process.env.WOLO_EPOCH_SOURCE_COMMIT||process.env.GITHUB_SHA;
if(expectedSource)assert.equal(g.source_sha,expectedSource,"Native golden source provenance");
function publicKeysOnly(v:unknown){
 if(!v||typeof v!=="object")return;
 for(const [k,item] of Object.entries(v)){
  assert.doesNotMatch(k,/(private[_-]?key|seed|mnemonic|password|secret|credential)/i,"Private field in public golden");
  publicKeysOnly(item);
 }
}
publicKeysOnly(g);

// Explicit schemas, independent of JSON input property order. Unknown fields fail.
const allocationKeys=["market_id","leg_id","wager_id","side","amount_uwolo"];
const ticketKeys=["epoch_id","ticket_id","owner_uid","owner_wallet","owner_public_key_hex","funding_tx_hash","funding_message_index","original_funding_principal_uwolo","allocations","owner_signature"];
const wagerKeys=["wager_id","market_id","ticket_id","leg_id","owner_uid","side","principal_uwolo","funding_tx_hash","funding_message_index"];
const reserveKeys=["account","liabilities_uwolo","maximum_unknown_outflow_uwolo","gas_reserve_uwolo","operating_floor_uwolo","inventory_sha256","nonoverlap_sha256"];
const requestKeys=[
 "bank_state_height","bank_commit_height","bank_commit_hash","bank_app_hash",
 "protocol","command","chain_id","denom","epoch_id","operation_id","original_operation_id",
 "entitlement_id","owner_uid","owner_wallet","owner_public_key_hex","original_mandate_sha256",
 "wager_id","ticket_id","market_id","leg_id","funding_tx_hash","funding_message_index",
 "sender","recipient","amount_uwolo","memo","policy_sha256","source_commit","binary_sha256",
 "config_sha256","plan","tickets","resolution_evidence_sha256","vault_reserve","escrow_reserve",
 "nonce","reviewer_permit_id","issued_at","expires_at","owner_signature","reviewer_signature"];
function ordered(v:J,keys:string[]):J{
 assert.deepEqual(Object.keys(v).sort(),[...keys].sort(),"typed field set changed");
 return Object.fromEntries(keys.map(k=>[k,v[k]]));
}
function ticket(t:J,clearSignature=false):J{
 const v=ordered(t,ticketKeys);
 v.allocations=t.allocations.map((l:J)=>ordered(l,allocationKeys));
 if(clearSignature)v.owner_signature="";
 return v;
}
function request(r:J):J{
 const v=ordered(r,requestKeys);
 v.plan=ordered(r.plan,["epoch_id","market_id","resolution","wagers"]);
 v.plan.wagers=r.plan.wagers.map((w:J)=>ordered(w,wagerKeys));
 v.tickets=r.tickets.map((t:J)=>ticket(t));
 v.vault_reserve=ordered(r.vault_reserve,reserveKeys);
 v.escrow_reserve=ordered(r.escrow_reserve,reserveKeys);
 v.owner_signature="";v.reviewer_signature="";
 return v;
}
// Go encoding/json HTML-escapes these characters even inside nested JSON strings.
function goJSON(v:unknown):string{
 return JSON.stringify(v).replace(/[<>&\u2028\u2029]/g,c=>"\\u"+c.charCodeAt(0).toString(16).padStart(4,"0"));
}
function exactMessage(v:unknown,encoded:string,label:string){
 const got=Buffer.from(goJSON(v),"utf8"), expected=Buffer.from(encoded,"base64");
 assert.equal(got.toString("base64"),encoded===expected.toString("base64")?encoded:"NONCANONICAL_BASE64",label);
 assert.deepEqual(got,expected,label);
 return got;
}
assert.deepEqual(Buffer.from(goJSON(["<&>\u2028\u2029"])),Buffer.from('["\\u003c\\u0026\\u003e\\u2028\\u2029"]'));
for(const x of g.tickets){
 const t=x.ticket;
 const msg=exactMessage([PROTOCOL,"original-ticket","wolo-1","uwolo",p.vault,p.escrow,
  "aoe2war/satchel/epoch-v3/"+t.epoch_id+"/ticket/"+t.ticket_id,ticket(t,true)],x.message_b64,"OriginalTicketMessage");
 assert.equal(sha(msg),x.digest_sha256);
}
for(const x of g.requests){
 const msg=exactMessage([PROTOCOL,request(x.request)],x.message_b64,"RequestMessage:"+x.name);
 assert.equal(sha(goJSON([PROTOCOL,msg.toString("utf8")])),x.fingerprint,"Fingerprint:"+x.name);
 // Reversing semantic input property order must produce identical canonical bytes.
 const reversed=Object.fromEntries(Object.entries(x.request).reverse());
 assert.equal(goJSON([PROTOCOL,request(reversed)]),msg.toString("utf8"));
}
const tickets=g.tickets.map((x:J)=>x.ticket);
assert.equal(tickets.length,2);
const alpha=tickets.find((t:J)=>t.ticket_id===200), beta=tickets.find((t:J)=>t.ticket_id===300);
assert.ok(alpha&&beta);
assert.equal(alpha.original_funding_principal_uwolo,"100000000");
assert.equal(beta.original_funding_principal_uwolo,"40000000");
const fundingInput=(t:J)=>({
 chainId:"wolo-1" as const,epochId:t.epoch_id,ownerUid:t.owner_uid,
 operationId:"satchel:e3:"+t.epoch_id+":"+t.ticket_id,ticketId:t.ticket_id,
 txHash:t.funding_tx_hash,messageIndex:t.funding_message_index,
 totalUwolo:t.original_funding_principal_uwolo,
 legs:t.allocations.map((l:J)=>({marketId:l.market_id,legId:l.leg_id,amountUwolo:l.amount_uwolo}))
});
for(const t of tickets){
 const x=inspectEpochV3TicketFunding(fundingInput(t));
 assert.equal(x.onePhysicalFundingReceipt,"wolo-1:"+t.funding_tx_hash+":0");
 assert.equal(x.totalFundingUwolo,t.original_funding_principal_uwolo);
 assert.equal(x.financialCreditAuthorized,false);
}
assert.deepEqual(alpha.allocations.map((x:J)=>x.amount_uwolo),["40000000","60000000"]);
const orig=fundingInput(alpha);
assert.throws(()=>inspectEpochV3TicketFunding({...orig,totalUwolo:"99000000"}),/conserve/);
assert.throws(()=>inspectEpochV3TicketFunding({...orig,totalUwolo:"101000000"}),/conserve/);
assert.throws(()=>inspectEpochV3TicketFunding({...orig,messageIndex:1}),/invalid_original_ticket/);
assert.throws(()=>inspectEpochV3TicketFunding({...orig,legs:[orig.legs[0],orig.legs[0]]}),/duplicated_economic_leg/);
assert.throws(()=>inspectEpochV3TicketFunding({...orig,legs:[{...orig.legs[0],amountUwolo:"40000001"},orig.legs[1]]}),/whole_wolo/);
function hdPlan(market:number,winner:"left"|"right"|null){
 return planNewEpochMarketSettlement({epochId:p.epoch_id,marketId:market,winningSide:winner,
  wagers:tickets.flatMap((t:J)=>t.allocations.filter((a:J)=>a.market_id===market).map((a:J)=>({
   wagerId:a.wager_id,marketId:a.market_id,ticketId:t.ticket_id,legId:a.leg_id,ownerUid:t.owner_uid,
   side:a.side,principalWolo:Number(BigInt(a.amount_uwolo)/1000000n),
   originalOperationId:"satchel:e3:"+p.epoch_id+":"+t.ticket_id,
   fundingTxHash:t.funding_tx_hash,fundingMessageIndex:0
  })))});
}
const plans=[hdPlan(77,"left"),hdPlan(78,null)];
assert.deepEqual(plans.map(x=>[x.totalReturnUwolo,x.totalFeeUwolo]),[["78000000","2000000"],["60000000","0"]]);
for(const plan of plans){
 const native=g.outcomes["market_"+plan.marketId];
 assert.equal(native.length,plan.entitlements.length);
 for(const h of plan.entitlements){
  const n=native.find((x:J)=>x.wager.wager_id===h.wagerId);
  assert.ok(n,"native outcome missing");
  assert.equal(h.payoutUwolo,n.payout_uwolo);
  assert.equal(h.feeUwolo,n.fee_uwolo);
  assert.equal(h.entitlementId,"satchel:e3:"+p.epoch_id+":entitlement:"+h.marketId+":"+h.ticketId+":"+h.legId);
 }
 assert.equal(plan.executionAuthorized,false);
}
const loser=plans[0].entitlements.find(x=>x.ticketId===300)!;
assert.equal(loser.kind,"unmatched_refund");assert.equal(loser.payoutUwolo,"0");
// A distinct held HD limitation: SQL and Go can conserve multiple same-market
// legs, while this exact HD planner still rejects a repeated original receipt.
assert.throws(()=>planNewEpochMarketSettlement({epochId:p.epoch_id,marketId:77,winningSide:"left",
 wagers:alpha.allocations.map((a:J)=>({wagerId:a.wager_id,marketId:77,ticketId:200,
  legId:a.leg_id,ownerUid:alpha.owner_uid,side:"left",principalWolo:Number(BigInt(a.amount_uwolo)/1000000n),
  originalOperationId:"satchel:e3:"+p.epoch_id+":200",fundingTxHash:alpha.funding_tx_hash,fundingMessageIndex:0}))
}),/duplicate_funding_or_leg/);
for(const f of [...g.funding,...g.effects]){
 assert.equal(sha(Buffer.from(f.tx_bytes_b64,"base64")).toUpperCase(),f.tx_hash,"native original tx bytes/hash");
 assert.equal(f.receipt.chain_id,"wolo-1");assert.equal(f.receipt.tx_hash,f.tx_hash);
 assert.equal(f.receipt.message_index,0);
 assert.ok(f.proof.responses.length>0,"portable native proof missing");
}
const effects=new Map(g.effects.map((x:J)=>[x.name,x]));
assert.equal(new Set(g.effects.map((x:J)=>x.tx_hash)).size,3);
const ret=effects.get("matched_return") as J, fee=effects.get("matched_fee") as J, voided=effects.get("void_return") as J;
assert.ok(ret&&fee&&voided);
assert.deepEqual([ret.intent.amount_uwolo,fee.intent.amount_uwolo,voided.intent.amount_uwolo],["78000000","2000000","60000000"]);
assert.equal(ret.intent.sender,p.escrow);assert.equal(ret.intent.recipient,p.vault);
assert.equal(voided.intent.sender,p.escrow);assert.equal(voided.intent.recipient,p.vault);
assert.equal(fee.intent.sender,p.escrow);assert.equal(fee.intent.recipient,p.fee_recipient);

const summary:J={
 qualification:"GENUINE_GO_NATIVE_ARTIFACT_TO_ACTUAL_HD_SOURCE_DISPOSABLE_ADAPTER",
 hd_commit:HD,golden_sha256:sha(rawGolden),source_files_verified:manifest.files.length,
 canonical_encoder:"Wolo-owned typed ordered Go JSON compatibility adapter; HD has no encoder",
 native_authentication:"Go native test authenticates Comet/ICS23 before export; this TS script is not a native verifier",
 financial_authority:false,production_custody_available:false,
 typed_ticket_messages:g.tickets.length,typed_request_messages:g.requests.length,
 economic_markets:plans.length,matched_return_uwolo:"78000000",fee_uwolo:"2000000",void_return_uwolo:"60000000",
 known_hd_mismatches:mismatch.mismatches,postgres:"NOT_RUN"
};
if(!process.argv.includes("--economics-only")){
 const dsn=process.env.WOLO_EPOCH_HD940_TEST_PG_DSN;
 assert.ok(dsn,"Full qualification requires explicit disposable WOLO_EPOCH_HD940_TEST_PG_DSN");
 const u=new URL(dsn!);
 assert.ok(["postgres:","postgresql:"].includes(u.protocol)&&["127.0.0.1","localhost"].includes(u.hostname));
 assert.equal(u.pathname,"/epoch_v3_hd940","Never fall back to DATABASE_URL or another database");
 const modules=process.env.WOLO_EPOCH_HD940_NODE_MODULES;
 const require=modules?createRequire(path.join(path.resolve(modules),"package.json")):createRequire(import.meta.url);
 const pg=require("pg");
 const c=new pg.Client({connectionString:dsn,connectionTimeoutMillis:5000,statement_timeout:10000});
 await c.connect();
 try{
  assert.match((await c.query("SHOW server_version")).rows[0].server_version,/^16\./);
  assert.equal((await c.query("SELECT count(*)::int AS n FROM pg_namespace WHERE nspname='epoch_v3'")).rows[0].n,0,"Disposable empty schema required");
  await c.query(readFileSync(new URL("prisma/migrations/20261027023000_epoch_v3_held_financial_ledger/migration.sql",base),"utf8"));
  await c.query(readFileSync(new URL("prisma/migrations/20261027040000_epoch_v3_native_proof_provenance/migration.sql",base),"utf8"));
  await c.query(readFileSync(new URL("scripts/review/epoch_v3_roles_install_held.sql",base),"utf8"));
  const E=p.epoch_id, fixedSha="a".repeat(64), firstRequest=g.requests[0].request;
  await c.query("INSERT INTO epoch_v3.epochs(epoch_id,h_star,vault_address,escrow_address,signer_policy_sha256) VALUES($1,$2,$3,$4,$5)",
   [E,p.h_star,p.vault,p.escrow,firstRequest.policy_sha256]);
  // Explicit fixture opening inventory; not represented as an authenticated deposit.
  for(const t of tickets){
   await c.query("INSERT INTO epoch_v3.positions(epoch_id,owner_uid,available_uwolo) VALUES($1,$2,$3)",[E,t.owner_uid,t.original_funding_principal_uwolo]);
   await c.query("INSERT INTO epoch_v3.balance_events(epoch_id,source_kind,source_key,owner_uid,available_delta) VALUES($1,'fixture_opening',$2,$3,$4)",[E,"fixture-opening:"+t.ticket_id,t.owner_uid,t.original_funding_principal_uwolo]);
  }
  const insert=async(table:string,obj:J)=>{
   const columns=Object.keys(obj);
   return c.query("INSERT INTO epoch_v3."+table+"("+columns.join(",")+") VALUES("+columns.map((_,i)=>"$"+(i+1)).join(",")+")",Object.values(obj));
  };
  const bankSeen=new Set<string>();
  function bankFresh(b:J){
   assert.equal(b.current_vault,true);assert.equal(b.current_escrow,true);
   assert.equal(b.commit_height,b.state_height+1);assert.equal(b.head_height,b.commit_height);
   assert.equal(b.app_root_equal,true);assert.equal(b.commit_hash_equal,true);assert.equal(b.head_hash_equal,true);
   for(const role of ["vault","escrow"]){
    assert.equal(b[role+"_state_height"],b.state_height);
    assert.equal(b[role+"_commit_height"],b.commit_height);
    assert.equal(b[role+"_head_height"],b.head_height);
   }
   const observed=Date.parse(b.observed_at),expires=Date.parse(b.expires_at),now=Date.now();
   assert.ok(Number.isFinite(observed)&&observed<=now&&expires>now&&expires-observed<=120000,"Fresh Go-authenticated bank artifact required; never rewrite its timestamps");
  }
  async function banks(b:J,deficit?:"vault"|"escrow",deduplicate=true){
   bankFresh(b);
   // Complete disposable-fixture obligations at this authenticated checkpoint.
   // The original request excludes its own debit from 'other liabilities', so
   // copying that request's reserve forever would misstate later inventory.
   let escrowLiability=tickets.reduce((n:bigint,t:J)=>n+BigInt(t.original_funding_principal_uwolo),0n);
   let vaultLiability=0n;
   for(const effect of g.effects){
    if(effect.height>=b.state_height)continue;
    escrowLiability-=BigInt(effect.intent.amount_uwolo);
    if(effect.intent.recipient===p.vault)vaultLiability+=BigInt(effect.intent.amount_uwolo);
   }
   assert.ok(escrowLiability>=0n);
   for(const role of ["vault","escrow"] as const){
    const key=role+":"+b.state_height;if(deduplicate&&bankSeen.has(key))continue;
    const reserve=firstRequest[role+"_reserve"],balance=b[role+"_balance_uwolo"];
    assert.match(balance,/^(0|[1-9][0-9]*)$/);
    await insert("native_account_reserve_evidence",{
     epoch_id:E,account_role:role,chain_id:"wolo-1",bank_state_height:b.state_height,
     bank_commit_height:b.commit_height,block_sha256:b.commit_hash,app_sha256:b.app_hash,
     bank_balance_uwolo:balance,liabilities_uwolo:deficit===role?(BigInt(balance)+1n).toString():(role==="vault"?vaultLiability:escrowLiability).toString(),
     maximum_unknown_outflow_uwolo:reserve.maximum_unknown_outflow_uwolo,
     gas_uwolo:reserve.gas_reserve_uwolo,operating_floor_uwolo:reserve.operating_floor_uwolo,
     inventory_sha256:sha(goJSON(["disposable-fixture-liabilities",role,b.state_height,vaultLiability.toString(),escrowLiability.toString()])),
     nonoverlap_sha256:sha(goJSON(["disposable-fixture-independent-account-domains",p.vault,p.escrow])),
     proof_sha256:sha(goJSON(b[role+"_proof"])),observed_at:b.observed_at,expires_at:b.expires_at
    });
    if(deduplicate)bankSeen.add(key);
   }
  }
  async function receipt(f:J,b:J,owner:string,kind:string,wrongRoot=false,wrongMemo=false){
   bankFresh(b);assert.ok(b.state_height>=f.height+2);
   const proofSha=sha(goJSON(f.proof)),memo=wrongMemo?"altered-native-memo":f.intent.memo;
   await insert("receipts",{chain_id:"wolo-1",tx_hash:f.tx_hash,message_index:0,epoch_id:E,owner_uid:owner,
    kind,sender:f.intent.sender,recipient:f.intent.recipient,memo,amount_uwolo:f.intent.amount_uwolo,
    chain_height:f.height,native_proof_sha256:proofSha,proof_verified_at:b.observed_at,chain_time:f.chain_time});
   await insert("native_proof_certificates",{
    chain_id:"wolo-1",tx_hash:f.tx_hash,message_index:0,epoch_id:E,owner_uid:owner,purpose:kind,denom:"uwolo",
    sender:f.intent.sender,recipient:f.intent.recipient,memo,amount_uwolo:f.intent.amount_uwolo,
    funding_height:f.height,bank_state_height:b.state_height,bank_commit_height:b.commit_height,
    root_app_sha256:wrongRoot?"F".repeat(64):b.app_hash,root_block_sha256:b.commit_hash,
    vault_account:p.vault,escrow_account:p.escrow,vault_bank_balance_uwolo:b.vault_balance_uwolo,
    escrow_bank_balance_uwolo:b.escrow_balance_uwolo,proof_sha256:proofSha,
    native_verifier_source:p.source_commit,native_verifier_binary_sha256:p.binary_sha256,
    trust_anchor_sha256:sha(goJSON(p.trust_anchor)),verification_record_sha256:sha(f.tx_hash+":"+kind),
    observed_at:b.observed_at,expires_at:b.expires_at,
    issuer_provenance:"disposable-adapter-from-genuine-native-Go-golden-not-held-ingress"
   });
  }
  const fund=(t:J)=>g.funding.find((f:J)=>f.tx_hash===t.funding_tx_hash);
  const admit=(t:J,legs=t.allocations,owner=t.owner_uid,epoch=E,index=0)=>
   c.query("SELECT epoch_v3.admit_ticket($1,$2,$3,$4,$5,$6,$7,$8::jsonb)",
    [epoch,owner,t.ticket_id,t.funding_tx_hash,index,fund(t).chain_time.slice(0,10),g.tickets.find((x:J)=>x.ticket.ticket_id===t.ticket_id).digest_sha256,JSON.stringify(legs)]);
  const negative:string[]=[];
  async function reject(name:string,setup:()=>Promise<unknown>,work:()=>Promise<unknown>,pattern:RegExp){
   await c.query("BEGIN ISOLATION LEVEL SERIALIZABLE");
   try{await setup();await assert.rejects(work,pattern,name);negative.push(name);}
   finally{await c.query("ROLLBACK");}
  }
  const fresh=async()=>{
   await banks(g.bank,undefined,false);await receipt(fund(alpha),g.bank,alpha.owner_uid,"wager_funding");
  };
  await reject("oversplit",fresh,()=>admit(alpha,alpha.allocations.map((x:J,i:number)=>({...x,amount_uwolo:i?"61000000":x.amount_uwolo}))),/TICKET_ALLOCATION_EXCEEDS_FUNDING/);
  await reject("undersplit",fresh,()=>admit(alpha,alpha.allocations.map((x:J,i:number)=>({...x,amount_uwolo:i?"59000000":x.amount_uwolo}))),/TICKET_ALLOCATION_EXCEEDS_FUNDING/);
  await reject("duplicate_leg",fresh,()=>admit(alpha,[{...alpha.allocations[0],amount_uwolo:"50000000"},{...alpha.allocations[0],amount_uwolo:"50000000"}]),/duplicate key/);
  await reject("wrong_owner",fresh,()=>admit(alpha,alpha.allocations,beta.owner_uid),/WRONG_OR_UNFUNDED_TICKET/);
  await reject("wrong_epoch",async()=>{
   await fresh();await c.query("INSERT INTO epoch_v3.epochs VALUES($1,$2,$3,$4,$5,'HELD_NONEXECUTING')",[E+"_other",p.h_star,p.vault,p.escrow,fixedSha]);
  },()=>admit(alpha,alpha.allocations,alpha.owner_uid,E+"_other"),/WRONG_OR_UNFUNDED_TICKET/);
  await reject("wrong_ordinal",fresh,()=>admit(alpha,alpha.allocations,alpha.owner_uid,E,1),/no rows/);
  await reject("changed_memo",async()=>{await banks(g.bank,undefined,false);await receipt(fund(alpha),g.bank,alpha.owner_uid,"wager_funding",false,true);},()=>admit(alpha),/WRONG_OR_UNFUNDED_TICKET/);
  await reject("changed_root",async()=>{await banks(g.bank,undefined,false);await receipt(fund(alpha),g.bank,alpha.owner_uid,"wager_funding",true);},()=>admit(alpha),/BANK_PROOF_STALE_OR_ACCOUNT_RESERVE_DEFICIT/);
  for(const role of ["vault","escrow"] as const)await reject(role+"_deficit",async()=>{
   await banks(g.bank,role,false);await receipt(fund(alpha),g.bank,alpha.owner_uid,"wager_funding");
  },()=>admit(alpha),/BANK_PROOF_STALE_OR_ACCOUNT_RESERVE_DEFICIT/);
  await banks(g.bank);
  for(const t of tickets){await receipt(fund(t),g.bank,t.owner_uid,"wager_funding");await admit(t);}
  await reject("physical_receipt_replay",async()=>{},()=>c.query("SELECT epoch_v3.consume_receipt($1,$2,'wager_funding',$3,0,$4,$5,$6,'changed-operation')",
   [E,alpha.owner_uid,alpha.funding_tx_hash,alpha.original_funding_principal_uwolo,p.vault,p.escrow]),/PHYSICAL_RECEIPT_ALREADY_CONSUMED/);
  assert.equal((await c.query("SELECT count(*)::int n FROM epoch_v3.receipt_consumptions WHERE tx_hash=$1",[alpha.funding_tx_hash])).rows[0].n,1);
  assert.deepEqual((await c.query("SELECT principal_uwolo::text p FROM epoch_v3.allocations WHERE ticket_id=200 ORDER BY market_id")).rows.map((x:J)=>x.p),["40000000","60000000"]);
  for(const plan of plans){
   const outcomes=plan.entitlements.map(h=>({ticket_id:h.ticketId,leg_id:h.legId,wager_id:h.wagerId,owner_uid:h.ownerUid,amount_uwolo:h.payoutUwolo,fee_uwolo:h.feeUwolo,kind:h.kind}));
   await c.query("SELECT epoch_v3.settle_market($1,$2,$3,$4,$5,$6::jsonb)",[E,plan.marketId,plan.marketId===77?"left":"void",fixedSha,sha(goJSON(plan)),JSON.stringify(outcomes)]);
  }
  const finalBank=g.final_bank;
  await banks(finalBank);
  for(const [effectName,purpose] of [["matched_return","escrow_return"],["void_return","escrow_return"],["matched_fee","fee"]]){
   const f=effects.get(effectName) as J,b=f.bank||finalBank;
   await banks(b);await receipt(f,b,alpha.owner_uid,purpose);
   const r=g.requests.find((x:J)=>x.name===effectName).request;
   if(purpose==="escrow_return"){
    const q="SELECT epoch_v3.reconcile_return($1,$2,$3,0,$4,$5,$6,$7)";
    const args=[E,r.entitlement_id,f.tx_hash,f.intent.amount_uwolo,p.escrow,p.vault,r.operation_id];
    await c.query(q,args);
    await reject(effectName+"_replay",async()=>{},()=>c.query(q,args),/PHYSICAL_RECEIPT_ALREADY_CONSUMED/);
   }else{
    // Existing generic physical-consumption routine; no user balance credit.
    const q="SELECT epoch_v3.consume_receipt($1,$2,'fee',$3,0,$4,$5,$6,$7)";
    const args=[E,alpha.owner_uid,f.tx_hash,f.intent.amount_uwolo,p.escrow,p.fee_recipient,r.operation_id];
    await c.query(q,args);
    await reject("fee_replay",async()=>{},()=>c.query(q,args),/PHYSICAL_RECEIPT_ALREADY_CONSUMED/);
   }
  }
  assert.equal((await c.query("SELECT count(*)::int n FROM epoch_v3.receipt_consumptions")).rows[0].n,5);
  assert.equal((await c.query("SELECT count(*)::int n FROM epoch_v3.return_effects")).rows[0].n,2);
  const positions=(await c.query("SELECT owner_uid,available_uwolo::text a,reserved_uwolo::text r,pending_uwolo::text p FROM epoch_v3.positions ORDER BY owner_uid")).rows;
  assert.deepEqual(positions.find((x:J)=>x.owner_uid===alpha.owner_uid),{owner_uid:alpha.owner_uid,a:"138000000",r:"0",p:"0"});
  assert.deepEqual(positions.find((x:J)=>x.owner_uid===beta.owner_uid),{owner_uid:beta.owner_uid,a:"0",r:"0",p:"0"});
  assert.ok((await c.query("SELECT exact FROM epoch_v3.position_reconciliation")).rows.every((x:J)=>x.exact));
  await reject("immutable_receipt",async()=>{},()=>c.query("UPDATE epoch_v3.receipts SET amount_uwolo=1 WHERE tx_hash=$1",[alpha.funding_tx_hash]),/IMMUTABLE_FINANCIAL_HISTORY/);
  summary.postgres="PASS_PG16_DISPOSABLE_ACTUAL_HD_SQL";
  summary.sql_negative_cases=negative;
  summary.sql_physical_consumptions=5;summary.sql_return_effects=2;
  summary.fixture_opening_inventory="100+40 WOLO source-only ledger inventory; not authenticated deposits";
  summary.sql_positions=positions;
 }finally{await c.end();}
}
process.stdout.write(JSON.stringify(summary,null,2)+"\n");
