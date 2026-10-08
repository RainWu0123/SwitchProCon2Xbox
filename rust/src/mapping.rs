//! Driver-neutral XUSB state and Switch button mapping.
use crate::input::{button as b,InputState};
pub mod xusb{
    pub const UP:u16=1;pub const DOWN:u16=2;pub const LEFT:u16=4;pub const RIGHT:u16=8;
    pub const START:u16=0x10;pub const BACK:u16=0x20;pub const L3:u16=0x40;
    pub const R3:u16=0x80;pub const LB:u16=0x100;pub const RB:u16=0x200;
    pub const GUIDE:u16=0x400;pub const A:u16=0x1000;pub const B:u16=0x2000;
    pub const X:u16=0x4000;pub const Y:u16=0x8000;
}
#[derive(Debug,Copy,Clone,PartialEq,Eq)]
pub enum Layout{Xbox,Nintendo}
#[derive(Debug,Default,Copy,Clone,PartialEq,Eq)]
pub struct XboxState{
    pub buttons:u16,pub lx:i16,pub ly:i16,pub rx:i16,pub ry:i16,
    pub lt:u8,pub rt:u8,
}
#[derive(Debug,Copy,Clone)]
pub struct Mapper{pub layout:Layout,pub deadzone:f32,pub invert_y:bool}
impl Mapper{
    pub fn new(layout:Layout,deadzone:f32,invert_y:bool)->Result<Self,String>{
        if !deadzone.is_finite()||!(0.0..=0.99).contains(&deadzone){
            return Err("deadzone must be a finite value in 0.0..=0.99".into());
        }
        Ok(Self{layout,deadzone,invert_y})
    }
    fn stick(&self,raw_x:u16,raw_y:u16)->(i16,i16){
        let mut x=((raw_x as f32)-2048.0)/2048.0;
        let mut y=((raw_y as f32)-2048.0)/2048.0;
        if self.invert_y{y=-y;}
        x=x.clamp(-1.0,1.0);y=y.clamp(-1.0,1.0);
        let mag=x.hypot(y);
        if mag<=self.deadzone{return(0,0);}
        let scale=((mag-self.deadzone)/(1.0-self.deadzone)).clamp(0.0,1.0)/mag;
        ((x*scale*32767.0) as i16,(y*scale*32767.0) as i16)
    }
    pub fn map(&self,input:InputState)->XboxState{
        let mut buttons=0u16;
        let face=match self.layout{
            Layout::Xbox=>[(b::A,xusb::A),(b::B,xusb::B),(b::X,xusb::X),(b::Y,xusb::Y)],
            Layout::Nintendo=>[(b::A,xusb::B),(b::B,xusb::A),(b::X,xusb::Y),(b::Y,xusb::X)],
        };
        for(src,dst)in face{if input.pressed(src){buttons|=dst;}}
        for(src,dst)in [
            (b::L,xusb::LB),(b::R,xusb::RB),(b::PLUS,xusb::START),
            (b::MINUS,xusb::BACK),(b::HOME,xusb::GUIDE),
            (b::L3,xusb::L3),(b::R3,xusb::R3),
            (b::UP,xusb::UP),(b::DOWN,xusb::DOWN),
            (b::LEFT,xusb::LEFT),(b::RIGHT,xusb::RIGHT),
        ]{if input.pressed(src){buttons|=dst;}}
        let(lx,ly)=self.stick(input.lx,input.ly);
        let(rx,ry)=self.stick(input.rx,input.ry);
        XboxState{
            buttons,lx,ly,rx,ry,
            lt:if input.pressed(b::ZL){255}else{0},
            rt:if input.pressed(b::ZR){255}else{0},
        }
    }
}
#[cfg(test)]
mod tests{
    use super::*;
    #[test]
    fn layout_and_triggers(){
        let src=InputState{buttons:b::A|b::ZL|b::L3,..Default::default()};
        let m=Mapper::new(Layout::Xbox,0.05,true).unwrap().map(src);
        let n=Mapper::new(Layout::Nintendo,0.05,true).unwrap().map(src);
        assert_ne!(m.buttons&xusb::A,0);assert_ne!(n.buttons&xusb::B,0);
        assert_eq!(m.lt,255);assert_ne!(m.buttons&xusb::L3,0);
    }
    #[test]
    fn deadzone_and_y_axis(){
        let m=Mapper::new(Layout::Xbox,0.05,true).unwrap();
        assert_eq!(m.map(InputState::default()),XboxState::default());
        assert_eq!(m.map(InputState{lx:2050,..Default::default()}).lx,0);
        let out=m.map(InputState{lx:4095,ly:4095,..Default::default()});
        assert!(out.lx>0&&out.ly<0);
    }
    #[test]
    fn invalid_deadzone(){
        for z in [f32::NAN,-0.1,1.0]{assert!(Mapper::new(Layout::Xbox,z,true).is_err())}
    }
}
