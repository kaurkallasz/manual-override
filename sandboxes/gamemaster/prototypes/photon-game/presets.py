"""Named immutable map/tier preset revisions, owned by Photon Game."""
import copy
import json
import os
from pathlib import Path
import threading
import uuid
import horde_presets
from photon_game_runtime.settings import validate_settings, DEFAULTS


class Presets:
    def __init__(self,path):
        self.path,self.lock=Path(path),threading.RLock()
        self.state={'schema_version':1,'revision':0,'presets':[],'selected':{}}
        try:
            saved=json.loads(self.path.read_text())
            if not isinstance(saved,dict) or saved.get('schema_version')!=1 or not isinstance(saved.get('presets'),list) or not isinstance(saved.get('selected'),dict):
                raise ValueError('invalid level preset store')
            for preset in saved['presets']:
                _,errors=validate_settings(preset.get('settings'))
                if errors or type(preset.get('tier')) is not int or not 1<=preset['tier']<=4:
                    raise ValueError('invalid saved preset')
            self.state.update(saved)
        except FileNotFoundError: pass

    def snapshot(self):
        with self.lock:
            return {'contract':'photon.game.presets','version':1,'status':'ready',**copy.deepcopy(self.state)}

    def _save(self,state):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temp=self.path.with_name(self.path.name+'.'+uuid.uuid4().hex+'.tmp')
        try:
            with temp.open('w') as handle:
                json.dump({'schema_version':1,**state},handle,allow_nan=False)
                handle.flush();os.fsync(handle.fileno())
            os.replace(temp,self.path)
            fd=os.open(self.path.parent,os.O_RDONLY)
            try: os.fsync(fd)
            finally: os.close(fd)
            self.state=state
        finally:temp.unlink(missing_ok=True)

    @staticmethod
    def _append(state,map_id,tier,name,settings,**metadata):
        state['revision']+=1
        preset={'id':uuid.uuid4().hex,'campaign_id':'ltz','map_id':map_id,'tier':tier,'name':name,
                'settings':copy.deepcopy(settings),'revision':state['revision'],**metadata}
        state['presets'].append(preset)
        return preset

    def ensure_map(self,map_id,base):
        with self.lock:
            if any(p['map_id']==map_id for p in self.state['presets']):
                self._ensure_archer_family(map_id, base)
                self._ensure_horde_family(map_id, base)
                self._ensure_event_family(map_id, base)
                return
            state=copy.deepcopy(self.state)
            clean,errors=validate_settings(base)
            if errors:raise ValueError(str(errors))
            for tier in range(1,5):
                self._append(state,map_id,tier,'Preserved venue settings',clean,
                             evidence='global settings preserved during migration',family='legacy')
                candidate={**clean,'first_wave_delay_s':300.0,'wave_interval_s':95.0,
                           'release_rate_multiplier':1.0,'enemy_count_multiplier':.22,'difficulty_offset':0.0,
                           'enemy_core_damage_multiplier':.18,'enemy_tower_damage_multiplier':.35,
                           'defense_unit_health_percent':20.0,
                           'control_orc_multiplier_joint':1.0,'control_orc_multiplier_xyz':1.08,
                           'control_orc_multiplier_image':1.16,'control_orc_multiplier_cue':1.24,
                           'control_pace_multiplier_joint':1.0,'control_pace_multiplier_xyz':1.08,
                           'control_pace_multiplier_image':1.16,'control_pace_multiplier_cue':1.24}
                preset=self._append(state,map_id,tier,'Provisional 25-minute progression',candidate,
                    evidence='design candidate; June pickup tasks have no tier labels; August source unavailable',
                    family='progression',target_active_seconds=1500 if tier==1 else None,
                    measured_speed_factor=None,source_run_ids=[])
                state['selected'][f'{map_id}:{tier}']=preset['id']
            self._save(state)
            self._ensure_archer_family(map_id, base)
            self._ensure_horde_family(map_id, base)
            self._ensure_event_family(map_id, base)

    def _ensure_event_family(self,map_id,base):
        """One-time event rollout; retain old revisions and subsequent GM choices."""
        if any(p['map_id']==map_id and p.get('family')=='event-progression-v1' for p in self.state['presets']):return
        state=copy.deepcopy(self.state)
        for tier,factor in enumerate((1,2,8,10),1):
            selected=state['selected'].get(f'{map_id}:{tier}')
            previous=next((p for p in state['presets'] if p['id']==selected),None)
            settings={**DEFAULTS,**copy.deepcopy(previous['settings'] if previous else base)}
            settings['enemy_health_multiplier']=min(10,float(settings['enemy_health_multiplier'])*factor)
            clean,errors=validate_settings(settings)
            if errors:raise ValueError(str(errors))
            preset=self._append(state,map_id,tier,'Event progression',clean,
                family='event-progression-v1',previous_preset_id=previous['id'] if previous else None,
                evidence='Synthetic eight-turret traces: low-tier equipment loses ground at L3/L4; venue tuning provisional')
            state['selected'][f'{map_id}:{tier}']=preset['id']
        self._save(state)

    def _ensure_horde_family(self,map_id,base):
        state=copy.deepcopy(self.state)
        for tier in range(1,5):
            if any(p['map_id']==map_id and p['tier']==tier and p.get('family')==horde_presets.FAMILY and p.get('candidate_revision')==horde_presets.REVISION for p in state['presets']):continue
            seed=next((p['settings'] for p in reversed(state['presets']) if p['map_id']==map_id and p['tier']==tier and p.get('family')=='breaker-archer'),base)
            settings,errors=validate_settings(horde_presets.candidate(seed,tier))
            if errors:raise ValueError(str(errors))
            self._append(state,map_id,tier,horde_presets.NAME,settings,family=horde_presets.FAMILY,candidate_revision=horde_presets.REVISION,
                         evidence='Synthetic reference trace; human playtest pending; 1,000 active cap and 2,000 deferred cap')
        if state['revision']!=self.state['revision']:self._save(state)

    def _ensure_archer_family(self, map_id, base):
        """Append candidates once; preserve every existing revision/selection."""
        state = copy.deepcopy(self.state)
        for tier in range(1, 5):
            if any(p['map_id'] == map_id and p['tier'] == tier and p.get('family') == 'breaker-archer' for p in state['presets']):
                continue
            seed = next((p for p in reversed(state['presets']) if p['map_id'] == map_id
                         and p['tier'] == tier and p.get('family') == 'progression'), None)
            settings, errors = validate_settings({**(seed['settings'] if seed else base), 'breaker_attack_mode': 'ranged'})
            if errors:
                raise ValueError(str(errors))
            self._append(state, map_id, tier, 'Breaker archer candidate', settings,
                         family='breaker-archer', combat_rule_version=1,
                         evidence='red archer; tower-first targeting; shield-blocked arrows; candidate tuning')
        if state['revision'] != self.state['revision']:
            self._save(state)

    def command(self,value):
        with self.lock:
            if type(value.get('revision')) is not int or value['revision']!=self.state['revision']:
                raise ValueError('presets changed; reload before saving')
            state=copy.deepcopy(self.state)
            map_id,tier,name=value.get('map_id'),value.get('tier'),value.get('name')
            if not isinstance(map_id,str) or not 1<=len(map_id)<=160 or type(tier)is not int or not 1<=tier<=4:
                raise ValueError('map and control tier required')
            if not isinstance(name,str) or not 1<=len(name.strip())<=60:raise ValueError('preset name required')
            name=name.strip();key=f'{map_id}:{tier}';action=value.get('action')
            if action in ('load','rename'):
                matches=[p for p in state['presets'] if p['map_id']==map_id and p['tier']==tier and p['name']==name]
                if not matches:raise ValueError('preset not found')
                selected=matches[-1]
                if action=='rename':
                    new_name=value.get('new_name')
                    if not isinstance(new_name,str) or not 1<=len(new_name.strip())<=60:raise ValueError('new preset name required')
                    metadata={k:v for k,v in selected.items() if k not in ('id','name','revision','settings','map_id','tier')}
                    selected=self._append(state,map_id,tier,new_name.strip(),selected['settings'],**metadata)
            elif action in ('save','defaults'):
                if action=='defaults':
                    seed=next((p for p in state['presets'] if p['map_id']==map_id and p['tier']==tier and p.get('family')=='progression'),None)
                    if seed is None:raise ValueError('commission this map before restoring its tier defaults')
                    incoming=seed['settings']
                else:incoming=value.get('settings')
                if not isinstance(incoming,dict):raise ValueError('settings object required')
                settings,errors=validate_settings(incoming)
                if errors:raise ValueError(str(errors))
                family=value.get('family','progression')
                if family not in ('progression','practice','breaker-archer',horde_presets.FAMILY):raise ValueError('supported preset family required')
                selected=self._append(state,map_id,tier,name,settings,family=family,
                    evidence=str(value.get('evidence') or 'operator provisional tuning')[:500],
                    target_active_seconds=1500 if tier==1 else None,measured_speed_factor=None,source_run_ids=[])
            else:raise ValueError('unsupported preset action')
            state['selected'][key]=selected['id'];state['revision']+=1
            self._save(state)
            # Project defaults for old revisions without rewriting their record.
            public_selected={**copy.deepcopy(selected),'settings':{**DEFAULTS,**copy.deepcopy(selected['settings'])}}
            return {**self.snapshot(),'selected_preset':public_selected}

    def for_run(self,map_id,tier,fallback):
        self.ensure_map(map_id,fallback)
        with self.lock:
            selected=self.state['selected'].get(f'{map_id}:{tier}')
            preset=next((p for p in self.state['presets'] if p['id']==selected),None)
            return ({**DEFAULTS, **copy.deepcopy(preset['settings'])},copy.deepcopy(preset)) if preset else ({**DEFAULTS, **fallback},None)

    def family_for_map(self,map_id,fallback):
        return [self.for_run(map_id,tier,fallback) for tier in range(1,5)]
