//! Strict parsing of complete original Switch Pro and Switch 2 Pro HID reports.
//! Unknown/short reports are rejected; stale fields are never carried forward.
pub mod button {
    pub const A: u32=1<<0; pub const B: u32=1<<1;
    pub const X: u32=1<<2; pub const Y: u32=1<<3;
    pub const L: u32=1<<4; pub const R: u32=1<<5;
    pub const ZL: u32=1<<6; pub const ZR: u32=1<<7;
    pub const PLUS: u32=1<<8; pub const MINUS: u32=1<<9;
    pub const HOME: u32=1<<10; pub const CAPTURE: u32=1<<11;
    pub const L3: u32=1<<12; pub const R3: u32=1<<13;
    pub const UP: u32=1<<14; pub const DOWN: u32=1<<15;
    pub const LEFT: u32=1<<16; pub const RIGHT: u32=1<<17;
    pub const GL: u32=1<<18; pub const GR: u32=1<<19;
    pub const C: u32=1<<20;
}
pub const VENDOR_ID: u16=0x057e;
pub const SWITCH_PRO: u16=0x2009;
pub const SWITCH_2_PRO: u16=0x2069;

#[derive(Debug,Clone,Copy,PartialEq,Eq)]
pub struct InputState {
    pub buttons:u32,
    pub lx:u16,pub ly:u16,pub rx:u16,pub ry:u16,
    /// Raw battery field, not an inferred percentage.
    pub battery:u8,
}
impl Default for InputState {
    fn default()->Self{
        Self{buttons:0,lx:2048,ly:2048,rx:2048,ry:2048,battery:0}
    }
}
impl InputState {
    pub fn pressed(&self,flag:u32)->bool{self.buttons&flag!=0}
}
pub fn parse_report(pid:u16,data:&[u8])->Option<InputState>{
    if data.len()<12{return None;}
    let second_gen=match(pid,data[0]){
        (SWITCH_PRO,0x30|0x21)=>false,
        (SWITCH_2_PRO,0x09)=>true,
        _=>return None,
    };
    fn put(bits:&mut u32,byte:u8,mask:u8,flag:u32){
        if byte&mask!=0{*bits|=flag;}
    }
    let(b3,b4,b5)=(data[3],data[4],data[5]);
    use button::*;
    let mut bits=0u32;
    if second_gen{
        for(m,f)in [(0x01,B),(0x02,A),(0x04,Y),(0x08,X),
            (0x10,R),(0x20,ZR),(0x40,PLUS),(0x80,R3)]{put(&mut bits,b3,m,f);}
        for(m,f)in [(0x01,DOWN),(0x02,RIGHT),(0x04,LEFT),(0x08,UP),
            (0x10,L),(0x20,ZL),(0x40,MINUS),(0x80,L3)]{put(&mut bits,b4,m,f);}
        for(m,f)in [(0x01,HOME),(0x02,CAPTURE),(0x04,GR),
            (0x08,GL),(0x10,C)]{put(&mut bits,b5,m,f);}
    }else{
        for(m,f)in [(0x01,Y),(0x02,X),(0x04,B),(0x08,A),
            (0x40,R),(0x80,ZR)]{put(&mut bits,b3,m,f);}
        for(m,f)in [(0x01,MINUS),(0x02,PLUS),(0x04,R3),
            (0x08,L3),(0x10,HOME),(0x20,CAPTURE)]{put(&mut bits,b4,m,f);}
        for(m,f)in [(0x01,DOWN),(0x02,UP),(0x04,RIGHT),
            (0x08,LEFT),(0x40,L),(0x80,ZL)]{put(&mut bits,b5,m,f);}
    }
    Some(InputState{
        buttons:bits,
        lx:u16::from(data[6])|(u16::from(data[7]&0x0f)<<8),
        ly:u16::from(data[7]>>4)|(u16::from(data[8])<<4),
        rx:u16::from(data[9])|(u16::from(data[10]&0x0f)<<8),
        ry:u16::from(data[10]>>4)|(u16::from(data[11])<<4),
        battery:if second_gen{(data[2]>>2)&0x0f}else{(data[2]>>4)&0x0f},
    })
}
#[cfg(test)]
mod tests{
    use super::*;
    fn centered(report:u8)->[u8;64]{
        let mut b=[0u8;64];b[0]=report;b[7]=8;b[8]=128;b[10]=8;b[11]=128;b
    }
    #[test]
    fn original_face_buttons_and_center(){
        let mut b=centered(0x30);b[3]=0x08|0x80;b[5]=0x02;b[2]=0x80;
        let s=parse_report(SWITCH_PRO,&b).unwrap();
        assert!(s.pressed(button::A));assert!(s.pressed(button::ZR));
        assert!(s.pressed(button::UP));assert_eq!(s.battery,8);
        assert_eq!((s.lx,s.ly,s.rx,s.ry),(2048,2048,2048,2048));
    }
    #[test]
    fn switch2_clicks_are_independent_of_c_button(){
        let mut b=centered(0x09);
        b[3]=0x80;b[4]=0x80;b[5]=0x10|0x04|0x08;b[2]=0x24;
        let s=parse_report(SWITCH_2_PRO,&b).unwrap();
        for flag in [button::L3,button::R3,button::C,button::GL,button::GR]{
            assert!(s.pressed(flag));
        }
        assert_eq!(s.battery,9);
        b[3]=0;b[4]=0;
        let s=parse_report(SWITCH_2_PRO,&b).unwrap();
        assert!(!s.pressed(button::L3));assert!(!s.pressed(button::R3));
        assert!(s.pressed(button::C));
    }
    #[test]
    fn reject_partial_and_unknown_reports(){
        assert!(parse_report(SWITCH_PRO,&[0x30;11]).is_none());
        assert!(parse_report(SWITCH_PRO,&centered(0x3f)).is_none());
        assert!(parse_report(SWITCH_PRO,&centered(0x09)).is_none());
        assert!(parse_report(SWITCH_2_PRO,&centered(0x30)).is_none());
    }
}
