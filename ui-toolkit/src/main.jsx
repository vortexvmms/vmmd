import React, {useEffect} from 'react';
import {createRoot} from 'react-dom/client';
import {Users, Building2, Clock, ArrowUpRight, CheckCircle2} from 'lucide-react';
import AOS from 'aos';
import 'aos/dist/aos.css';
import {initFlowbite} from 'flowbite';
import {Button} from './components/ui/button';
import {Card,CardHeader,CardTitle,CardContent} from './components/ui/card';
import {Badge} from './components/ui/badge';
import {Input} from './components/ui/input';
import {Checkbox} from './components/ui/checkbox';
import {Dialog,DialogTrigger,DialogContent,DialogTitle,DialogDescription} from './components/ui/dialog';
import {BentoGrid,BentoGridItem} from './components/ui/bento-grid';
import './styles.css';
import './animista.css';
function App(){
 useEffect(()=>{initFlowbite();if(!matchMedia('(prefers-reduced-motion: reduce)').matches)AOS.init({duration:180,once:true});},[]);
 return <main className="vcms-fade-in mx-auto max-w-6xl p-5 md:p-10 space-y-8">
 <header className="flex flex-wrap items-center justify-between gap-4 border-b pb-6"><div><p className="text-xs font-bold uppercase tracking-widest text-primary">Vortex Construction Management System</p><h1 className="mt-2 text-3xl font-semibold">UI development workspace</h1><p className="mt-2 text-muted-foreground">Component examples · sample data only</p></div><Badge variant="secondary">Free component toolkit</Badge></header>
 <BentoGrid className="md:auto-rows-[12rem]">{[[Users,'Workforce','Attendance and allocation'],[Building2,'Site operations','Daily progress and reports'],[Clock,'Follow-up','Pending records and end times']].map(([Icon,title,description])=><BentoGridItem key={title} title={title} description={description} icon={<Icon aria-hidden="true" className="text-primary"/>} header={<div className="h-12 rounded-lg bg-secondary"/>}/>)}</BentoGrid>
 <div className="grid gap-5 md:grid-cols-2"><Card><CardHeader><CardTitle>Daily workflow controls</CardTitle></CardHeader><CardContent className="space-y-5"><label className="block space-y-2">Search sites<Input placeholder="Enter a site name"/></label><label className="flex items-center gap-3"><Checkbox id="attendance"/>Attendance reviewed</label><div className="flex flex-wrap gap-3"><Dialog><DialogTrigger asChild><Button>Review example</Button></DialogTrigger><DialogContent><DialogTitle>Attendance review</DialogTitle><DialogDescription>This is a UI example. No worker records are loaded or changed.</DialogDescription></DialogContent></Dialog><Button variant="outline">Copy reminder</Button></div></CardContent></Card>
 <Card><CardHeader><CardTitle>Flowbite dropdown</CardTitle></CardHeader><CardContent><button id="site-trigger" data-dropdown-toggle="site-menu" className="rounded-lg bg-primary px-5 py-3 text-white focus-visible:outline-2" type="button">Example sites</button><div id="site-menu" className="z-10 hidden rounded-lg border bg-white shadow-md"><ul className="py-2 text-sm" aria-labelledby="site-trigger"><li className="px-4 py-2">Advario · sample</li><li className="px-4 py-2">PCS · sample</li></ul></div><p className="mt-5 text-sm text-muted-foreground">Vanilla JavaScript component support for existing VCMS pages.</p></CardContent></Card></div>
 <section className="rounded-xl border bg-white p-6"><h2 className="text-lg font-semibold">Uiverse checkbox adaptation</h2><p className="mt-1 text-sm text-muted-foreground">Based on AnthonyPreite's MIT checkbox, with keyboard focus and visible text.</p><label className="uiverse-check mt-4 inline-flex items-center gap-3"><input type="checkbox"/><span>Reviewed for today</span></label></section>
 <section className="rounded-xl border bg-white p-6" data-aos="fade-up"><div className="mx-auto flex flex-col items-start gap-5 sm:flex-row sm:items-center"><div className="flex-grow"><h2 className="text-2xl font-medium">Ready for your next site task</h2><p className="mt-2 text-muted-foreground">Tailblocks CTA layout adapted to the VCMS workflow.</p></div><Button asChild><a href="../home.html">Open VCMS home<ArrowUpRight aria-hidden="true"/></a></Button></div></section>
 <footer className="text-sm text-muted-foreground">shadcn/ui · Aceternity UI · Flowbite · Lucide · AOS · Tailblocks · Uiverse. See ui-toolkit/README.md for design resources and licences.</footer></main>;
}
createRoot(document.getElementById('root')).render(<App/>);
