/* Pickers open only from the original location/friend controls. */
window.FoodiemoPickers = {
    choose(kind, selected = []) {
        return new Promise(resolve => {
            const multiple=kind==='members', chosen=new Map(selected.map(x=>[String(x.id),x]));
            const dialog=document.createElement('dialog');
            dialog.style.cssText='width:min(92vw,420px);max-height:80vh;margin:auto;border:0;border-radius:24px;padding:24px;background:#F3ECE5;color:#5D4D40;font:16px system-ui';
            dialog.innerHTML='<h3></h3><input aria-label="搜尋" style="width:100%;margin:16px 0;padding:12px;border:1px solid #bba997;border-radius:12px"><div class="picker-status" role="status"></div><div class="picker-list" style="max-height:40vh;overflow:auto"></div><div style="display:flex;gap:10px;margin-top:16px"><button type="button" data-action="clear">清除選擇</button><button type="button" data-action="cancel">取消</button><button type="button" data-action="apply">完成</button></div>';
            dialog.querySelector('h3').textContent=multiple?'標註好友（已註冊會員）':'選擇餐廳地點';
            const input=dialog.querySelector('input'),list=dialog.querySelector('.picker-list'),status=dialog.querySelector('.picker-status');
            input.placeholder=multiple?'輸入至少兩個字搜尋名稱':'搜尋店名或地址';
            let controller,timer,version=0;
            const finish=value=>{clearTimeout(timer);controller?.abort();dialog.close();dialog.remove();resolve(value);};
            dialog.addEventListener('cancel',e=>{e.preventDefault();finish(null);});
            dialog.querySelector('[data-action=cancel]').onclick=()=>finish(null);
            dialog.querySelector('[data-action=apply]').onclick=()=>finish([...chosen.values()]);
            dialog.querySelector('[data-action=clear]').onclick=()=>{chosen.clear();search();};
            const show=items=>{
                list.replaceChildren();
                for(const item of items){
                    const button=document.createElement('button');
                    button.type='button';button.dataset.id=item.id;
                    button.style.cssText='display:block;width:100%;padding:12px;text-align:left;border:0;border-bottom:1px solid #dacbbc;background:transparent;color:inherit';
                    button.textContent=(chosen.has(item.id)?'✓ ':'')+item.name+(item.address?' · '+item.address:'');
                    button.setAttribute('aria-pressed',String(chosen.has(item.id)));
                    button.onclick=()=>{
                        if(chosen.has(item.id))chosen.delete(item.id);
                        else{if(!multiple)chosen.clear();if(chosen.size>=10){status.textContent='最多標註 10 人';return;}chosen.set(item.id,item);}
                        show(items);status.textContent='已選 '+chosen.size+' 項';
                    };
                    list.append(button);
                }
            };
            async function search(){
                const n=++version;controller?.abort();controller=new AbortController();
                if(multiple && input.value.trim().length<2){show([...chosen.values()]);status.textContent='請輸入至少兩個字；僅顯示會員名稱';return;}
                status.textContent='讀取中…';
                try{
                    const res=await fetch(DB_CONFIG.apiUrl+'/'+kind+'?q='+encodeURIComponent(input.value.trim()),{signal:controller.signal});
                    const data=await res.json();if(!res.ok)throw new Error(data.detail||'讀取失敗');
                    if(n!==version)return;show(data.items);status.textContent=data.items.length?'已選 '+chosen.size+' 項':'沒有符合的資料';
                }catch(e){if(n===version && e.name!=='AbortError')status.textContent='讀取失敗，請重新搜尋';}
            }
            input.oninput=()=>{clearTimeout(timer);timer=setTimeout(search,200);};
            document.body.append(dialog);dialog.showModal();input.focus();search();
        });
    }
};
