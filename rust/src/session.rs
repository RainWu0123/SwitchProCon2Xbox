//! Neutralize the virtual controller on disconnect, stale input, or shutdown.
use std::time::{Duration,Instant};
use crate::input::InputState;
use crate::mapping::{Mapper,XboxState};
pub trait VirtualPad{fn submit(&mut self,state:XboxState)->Result<(),String>;}
impl<T:VirtualPad+?Sized>VirtualPad for Box<T>{
    fn submit(&mut self,state:XboxState)->Result<(),String>{(**self).submit(state)}
}
pub struct Forwarder<T:VirtualPad>{
    pad:T,mapper:Mapper,timeout:Duration,
    last:XboxState,last_received:Option<Instant>,
}
impl<T:VirtualPad>Forwarder<T>{
    pub fn new(mut pad:T,mapper:Mapper,timeout:Duration)->Result<Self,String>{
        if timeout.is_zero(){return Err("timeout must be nonzero".into());}
        pad.submit(XboxState::default())?;
        Ok(Self{pad,mapper,timeout,last:XboxState::default(),last_received:None})
    }
    fn send(&mut self,state:XboxState)->Result<(),String>{
        if state!=self.last{
            self.pad.submit(state)?;
            self.last=state;
        }
        Ok(())
    }
    pub fn accept(&mut self,state:InputState,now:Instant)->Result<(),String>{
        self.send(self.mapper.map(state))?;
        self.last_received=Some(now);
        Ok(())
    }
    pub fn tick(&mut self,now:Instant)->Result<(),String>{
        if self.last_received.is_some_and(|t|now.saturating_duration_since(t)>=self.timeout){
            self.neutral()?;
        }
        Ok(())
    }
    pub fn neutral(&mut self)->Result<(),String>{
        self.send(XboxState::default())?;
        self.last_received=None;Ok(())
    }
}
impl<T:VirtualPad>Drop for Forwarder<T>{
    fn drop(&mut self){let _=self.pad.submit(XboxState::default());}
}
#[cfg(test)]
mod tests{
    use super::*;
    use crate::{input::button,mapping::Layout};
    #[derive(Default)]struct Mock{sent:Vec<XboxState>}
    impl VirtualPad for Mock{
        fn submit(&mut self,state:XboxState)->Result<(),String>{self.sent.push(state);Ok(())}
    }
    fn mapper()->Mapper{Mapper::new(Layout::Xbox,0.05,true).unwrap()}
    #[test]
    fn timeout_clears_pressed_buttons_exactly_once(){
        let t=Instant::now();
        let mut f=Forwarder::new(Mock::default(),mapper(),Duration::from_millis(150)).unwrap();
        f.accept(InputState{buttons:button::A,..Default::default()},t).unwrap();
        f.tick(t+Duration::from_millis(149)).unwrap();
        assert_eq!(f.pad.sent.len(),2);
        f.tick(t+Duration::from_millis(150)).unwrap();
        assert_eq!(f.pad.sent.len(),3);
        assert_eq!(f.pad.sent[2],XboxState::default());
        f.tick(t+Duration::from_secs(1)).unwrap();
        assert_eq!(f.pad.sent.len(),3);
    }
    #[test]
    fn disconnect_resets_sticks_and_triggers(){
        let t=Instant::now();
        let mut f=Forwarder::new(Mock::default(),mapper(),Duration::from_millis(150)).unwrap();
        f.accept(InputState{lx:4095,buttons:button::ZL,..Default::default()},t).unwrap();
        f.neutral().unwrap();
        assert_eq!(f.pad.sent.last().copied(),Some(XboxState::default()));
    }
}
