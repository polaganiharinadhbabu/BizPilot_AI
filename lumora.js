(() => {
  const API = window.BIZPILOT_API || "https://bizpilot-ai-api.onrender.com";
  const $ = id => document.getElementById(id);
  let token = sessionStorage.getItem("bp_token") || localStorage.getItem("bp_token") || "";
  let conversations = [], currentId = null, busy = false, toastTimer;
  const messages = $("messages"), input = $("messageInput"), send = $("sendButton");
  if (!token) { location.replace("index.html"); return; }
  async function api(path, options={}) {
    const response = await fetch(API + path, { ...options, headers: { "Content-Type":"application/json", Authorization:"Bearer "+token, ...(options.headers||{}) }});
    const data = response.status === 204 ? null : await response.json().catch(()=>({}));
    if (!response.ok) { if(response.status===401){sessionStorage.removeItem("bp_token");localStorage.removeItem("bp_token");location.replace("index.html");} throw new Error(data?.detail || "Request failed ("+response.status+")"); }
    return data;
  }
  function toast(text){const node=$("toast");node.textContent=text;node.classList.add("show");clearTimeout(toastTimer);toastTimer=setTimeout(()=>node.classList.remove("show"),2800);}
  function esc(s){return String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}
  function closeSidebar(){$("sidebar").classList.remove("open");$("mobileScrim").classList.remove("show");}
  function scrollBottom(){$("conversation").scrollTop=$("conversation").scrollHeight;}
  function showWelcome(){ $("welcome").hidden=false; messages.replaceChildren(); }
  function renderHistory(){
    const q=$("historySearch").value.trim().toLowerCase(), list=$("historyList");list.replaceChildren();
    const filtered=conversations.filter(c=>(c.title||"New chat").toLowerCase().includes(q));
    if(!filtered.length){const p=document.createElement("p");p.className="empty-history";p.textContent=q?"No matching chats.":"Your saved chats will appear here.";list.append(p);return;}
    filtered.forEach(c=>{const row=document.createElement("div");row.className="history-row"+(c.id===currentId?" active":"");
      const open=document.createElement("button");open.className="history-open";open.textContent=c.title||"New chat";open.title=c.title||"New chat";open.onclick=()=>openConversation(c.id).catch(e=>toast(e.message));
      const del=document.createElement("button");del.className="history-delete";del.textContent="×";del.title="Delete chat";del.setAttribute("aria-label","Delete "+(c.title||"chat"));del.onclick=async()=>{if(!confirm("Delete this conversation?"))return;try{await api("/chat/conversations/"+c.id,{method:"DELETE"});if(currentId===c.id){currentId=null;showWelcome();}await loadHistory();toast("Chat deleted.");}catch(e){toast(e.message)}};
      row.append(open,del);list.append(row);
    });
  }
  async function loadHistory(){conversations=await api("/chat/conversations");renderHistory();}
  function addMessage(item){
    if($("welcome"))$("welcome").hidden=true;
    const role=item.role==="user"?"user":"assistant",wrap=document.createElement("article");wrap.className="message "+role;wrap.dataset.id=item.id||"";
    const avatar=document.createElement("div");avatar.className="avatar";avatar.textContent=role==="user"?"H":"✦";
    const body=document.createElement("div");body.className="message-body";
    const label=document.createElement("div");label.className="message-label";label.textContent=role==="user"?"You":"Lumora";
    const bubble=document.createElement("div");bubble.className="bubble";bubble.textContent=item.content||"";
    body.append(label,bubble);
    if(role==="user"&&item.id){
      const actions=document.createElement("div");actions.className="message-actions";const edit=document.createElement("button");edit.className="message-action";edit.textContent="✎ Edit message";edit.onclick=()=>editMessage(item,wrap);actions.append(edit);body.append(actions);
    } else if(role==="assistant"){
      const actions=document.createElement("div");actions.className="message-actions";const copy=document.createElement("button");copy.className="message-action";copy.textContent="Copy";copy.onclick=async()=>{try{await navigator.clipboard.writeText(item.content);toast("Copied to clipboard.");}catch{toast("Could not copy on this browser.");}};actions.append(copy);body.append(actions);
    }
    wrap.append(avatar,body);messages.append(wrap);scrollBottom();return wrap;
  }
  async function openConversation(id){
    if(busy)return toast("Wait for Lumora to finish first.");
    const result=await api("/chat/conversations/"+id);currentId=result.conversation.id;messages.replaceChildren();$("welcome").hidden=true;
    if(!result.messages.length)showWelcome();else result.messages.forEach(addMessage);
    renderHistory();closeSidebar();scrollBottom();
  }
  async function newChat(){if(busy)return;currentId=null;showWelcome();renderHistory();closeSidebar();input.value="";input.focus();}
  async function sendMessage(text, existingId=null){
    if(busy||!text.trim())return;
    busy=true;input.disabled=true;send.disabled=true;
    const welcome=$("welcome");if(welcome)welcome.hidden=true;
    const typing=document.createElement("div");typing.className="typing";typing.textContent="Lumora is thinking…";messages.append(typing);scrollBottom();
    try{
      const result=await api("/chat/",{method:"POST",body:JSON.stringify({message:text.trim(),...(existingId||currentId?{conversation_id:existingId||currentId}:{})})});
      typing.remove();currentId=result.conversation_id;
      await openConversation(currentId);await loadHistory();
    }catch(e){typing.remove();toast(e.message);}
    finally{busy=false;input.disabled=false;send.disabled=false;input.focus();}
  }
  async function editMessage(item,wrap){
    if(busy)return toast("Wait for Lumora to finish first.");
    const body=wrap.querySelector(".message-body"),old=item.content;body.innerHTML="";
    const label=document.createElement("div");label.className="message-label";label.textContent="Edit your message";
    const area=document.createElement("textarea");area.className="message-edit";area.value=old;area.maxLength=10000;
    const controls=document.createElement("div");controls.className="edit-controls";
    const cancel=document.createElement("button");cancel.textContent="Cancel";cancel.onclick=()=>openConversation(currentId).catch(e=>toast(e.message));
    const save=document.createElement("button");save.className="save-edit";save.textContent="Save & regenerate";save.onclick=async()=>{
      const text=area.value.trim();if(!text)return toast("Message cannot be empty.");if(text===old)return openConversation(currentId);
      save.disabled=true;save.textContent="Updating…";
      try{
        await api("/chat/messages/"+item.id,{method:"PUT",body:JSON.stringify({content:text})});
        await sendMessage(text,currentId);toast("Message edited and regenerated.");
      }catch(e){toast(e.message);save.disabled=false;save.textContent="Save & regenerate";}
    };
    controls.append(cancel,save);body.append(label,area,controls);area.focus();area.setSelectionRange(area.value.length,area.value.length);
  }
  $("chatForm").addEventListener("submit",e=>{e.preventDefault();const text=input.value.trim();if(!text||busy)return;input.value="";input.style.height="auto";sendMessage(text);});
  input.addEventListener("input",()=>{input.style.height="auto";input.style.height=Math.min(input.scrollHeight,180)+"px";});
  input.addEventListener("keydown",e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();$("chatForm").requestSubmit();}});
  $("newChat").onclick=newChat;$("mobileNew").onclick=newChat;
  $("openSidebar").onclick=()=>{$("sidebar").classList.add("open");$("mobileScrim").classList.add("show");};
  $("mobileScrim").onclick=closeSidebar;$("historySearch").addEventListener("input",renderHistory);
  document.querySelectorAll("[data-prompt]").forEach(b=>b.addEventListener("click",()=>{input.value=b.dataset.prompt;input.focus();input.style.height="auto";input.style.height=input.scrollHeight+"px";}));
  $("logout").onclick=()=>{sessionStorage.removeItem("bp_token");localStorage.removeItem("bp_token");location.replace("index.html");};
  document.addEventListener("keydown",e=>{if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==="k"){e.preventDefault();newChat();}});
  loadHistory().then(()=>{const last=conversations[0];if(last)openConversation(last.id).catch(e=>toast(e.message));}).catch(e=>{toast(e.message);if(e.message==="Please log in.")location.replace("index.html");});
})();