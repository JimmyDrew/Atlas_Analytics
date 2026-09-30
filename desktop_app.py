"""Run with python desktop_app.py, or double-click Open Atlas.cmd on Windows."""
import os, queue, threading, uuid
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
from intake import prepare_submission, local_preview
from agents import request, run_team

ROOT = Path(__file__).resolve().parent

class AtlasApp:
    def __init__(self, window):
        self.window = window
        self.events = queue.Queue()
        self.busy = False
        window.title('Atlas Analytics | Upload and Ask')
        window.geometry('1060x800')
        window.minsize(800, 650)
        window.configure(bg='#eef2f7')
        style = ttk.Style(window)
        style.theme_use('clam')
        style.configure('TFrame', background='#eef2f7')
        style.configure('TLabel', background='#eef2f7', font=('Segoe UI', 10))
        style.configure('TButton', font=('Segoe UI', 10), padding=8)
        style.configure('Title.TLabel', font=('Segoe UI', 23, 'bold'), foreground='#132842')
        outer = ttk.Frame(window, padding=24)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='Atlas Analytics', style='Title.TLabel').pack(anchor='w')
        ttk.Label(outer, text='Upload a report. Ask a question. Review the evidence.').pack(anchor='w', pady=(2,16))
        row = ttk.Frame(outer); row.pack(fill='x')
        self.file = tk.StringVar()
        ttk.Entry(row, textvariable=self.file).pack(side='left', fill='x', expand=True)
        self.browse = ttk.Button(row, text='Choose file', command=self.choose)
        self.browse.pack(side='left', padx=8)
        self.example = ttk.Button(row, text='Try sample report', command=self.sample)
        self.example.pack(side='left')
        ttk.Label(outer, text='CSV, Excel (.xlsx), PDF, text, Markdown or JSON | up to 30 MB').pack(anchor='w', pady=(5,14))
        ttk.Label(outer, text='What would you like to know?').pack(anchor='w')
        self.question = ScrolledText(outer, height=3, font=('Segoe UI',11), wrap='word', relief='solid', bd=1)
        self.question.pack(fill='x', pady=(5,12))
        self.question.insert('1.0', 'Summarize the key findings, identify data quality issues, and suggest next steps.')
        settings = ttk.Frame(outer); settings.pack(fill='x')
        ttk.Label(settings, text='API key').grid(row=0,column=0,sticky='w')
        self.key = tk.StringVar(value=os.environ.get('OPENAI_API_KEY',''))
        ttk.Entry(settings,textvariable=self.key,show='*',width=36).grid(row=0,column=1,padx=(8,18),sticky='ew')
        ttk.Label(settings,text='Model').grid(row=0,column=2,sticky='w')
        self.model=tk.StringVar(value=os.environ.get('OPENAI_MODEL','gpt-5-mini'))
        ttk.Combobox(settings,textvariable=self.model,width=24,
            values=('gpt-5-mini','gpt-5.4-mini','gpt-5.5')).grid(row=0,column=3,padx=8,sticky='ew')
        settings.columnconfigure(1,weight=1); settings.columnconfigure(3,weight=1)
        ttk.Label(outer,text='AI mode sends extracted text or table statistics to OpenAI. API charges apply. Keys are not saved. Model IDs use lowercase.').pack(anchor='w',pady=(7,12))
        actions=ttk.Frame(outer);actions.pack(fill='x')
        self.preview=ttk.Button(actions,text='Preview locally (free)',command=lambda:self.submit(False));self.preview.pack(side='left')
        self.ask=ttk.Button(actions,text='Ask AI Team (paid)',command=lambda:self.submit(True));self.ask.pack(side='left',padx=8)
        ttk.Button(actions,text='Save response',command=self.save).pack(side='right')
        self.status=tk.StringVar(value='Choose a file or try the included sample report.')
        ttk.Label(outer,textvariable=self.status).pack(anchor='w',pady=(10,5))
        self.progress=ttk.Progressbar(outer,mode='indeterminate');self.progress.pack(fill='x',pady=(0,10))
        self.output=ScrolledText(outer,wrap='word',font=('Consolas',10),bg='#132238',fg='#e5edf9',insertbackground='white',padx=16,pady=16)
        self.output.pack(fill='both',expand=True)
        self.set_output('Your response will appear here.\n\nLocal preview works without an API key.\nAI mode runs five reviewers with explicit handoffs.\n\nPDF support reads selectable text; scanned pages need OCR.')
        window.after(100,self.poll)

    def set_output(self,text):
        self.output.configure(state='normal');self.output.delete('1.0','end')
        self.output.insert('1.0',text);self.output.configure(state='disabled')

    def choose(self):
        path=filedialog.askopenfilename(filetypes=[('Supported reports','*.csv *.xlsx *.pdf *.txt *.md *.json')])
        if path:self.file.set(path)

    def sample(self):
        self.file.set(str(ROOT/'artifacts'/'REPORT.md'))
        self.submit(False)

    def submit(self,live):
        if self.busy:return
        path=self.file.get().strip(); question=self.question.get('1.0','end').strip()
        key=self.key.get().strip();model=self.model.get().strip()
        if not Path(path).is_file():messagebox.showerror('Choose a file','Select an existing report first.');return
        if live and (not key or not model):messagebox.showerror('AI settings needed','Enter an API key and a model available to your API project. Local preview needs neither.');return
        if live and not question:messagebox.showerror('Question needed','Enter a question for the team.');return
        self.busy=True
        for button in (self.preview,self.ask,self.browse,self.example):button.state(['disabled'])
        self.progress.start(12)
        self.status.set('Reading your report…' if not live else 'Preparing evidence for the AI team…')
        self.set_output('Working…')
        threading.Thread(target=self.work,args=(path,question,live,key,model),daemon=True).start()

    def work(self,path,question,live,key,model):
        base=None
        try:
            evidence=prepare_submission(path,question)
            if not live:
                self.events.put(('done',local_preview(evidence)));return
            base=ROOT/'artifacts'/'submissions'/uuid.uuid4().hex
            def client(role,payload,selected_model):
                self.events.put(('status',f'AI team: {role} reviewer running…'))
                return request(role,payload,selected_model,api_key=key)
            records=run_team(evidence,model,client=client,output_dir=base)
            response='AI-GENERATED RESPONSE\n\n'+records['reporting']['text']
            response+='\n\nINPUT SCOPE\n'+'\n'.join('- '+v for v in evidence['limitations'])
            response+='\n\nSaved agent logs: '+str(base)
            self.events.put(('done',response))
        except Exception as error:
            message=str(error)
            if base:
                reviews=list(base.glob('*/NEEDS_REVIEW.md'))
                if reviews:message='The reviewer flagged issues; no final AI report was released.\n\n'+reviews[0].read_text(encoding='utf-8')
                message+='\n\nRun logs: '+str(base)
            self.events.put(('error',message))

    def poll(self):
        try:
            while True:
                kind,text=self.events.get_nowait()
                if kind=='status':self.status.set(text);continue
                self.set_output(text);self.status.set('Response ready.' if kind=='done' else 'Could not finish. See details below.')
                self.progress.stop();self.busy=False
                for button in (self.preview,self.ask,self.browse,self.example):button.state(['!disabled'])
        except queue.Empty:pass
        self.window.after(100,self.poll)

    def save(self):
        if self.busy:messagebox.showinfo('Still working','Wait for the response before saving.');return
        path=filedialog.asksaveasfilename(defaultextension='.md',initialfile='atlas-response.md',filetypes=[('Markdown','*.md'),('Text','*.txt')])
        if path:
            try:Path(path).write_text(self.output.get('1.0','end'),encoding='utf-8')
            except OSError as error:messagebox.showerror('Save failed',str(error))

if __name__=='__main__':
    root=tk.Tk();app=AtlasApp(root);root.mainloop()
