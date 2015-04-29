delimiter //

drop function if exists base32_encode//
create function base32_encode
    (hash varchar(255) character set latin1) 
    returns varchar(255) character set latin1 
    no sql begin

    declare len tinyint /* static */ unsigned default length(hash); -- length of string
    declare chu tinyint /* static */ unsigned default 15; -- chunk size
    declare off tinyint unsigned default len; -- offset for substr, start at the very end
    declare inn  bigint unsigned; -- integer chunk for inner loop
    declare wrk tinyint unsigned default 0; -- working value for mapping
    declare ret varchar(255) character set latin1 default ''; -- result

    -- each base32 char is 5 bits. each hex char is 4 bits.
    -- we have to work with chunks that share those factors.
    -- the biggest we can do while staying below 64 bits is
    -- 5 * 4 * 3 = 60 bits, so 15 hex characters at a time.
    while off > 0 do
        set off= if(off>=chu,off-chu,0);
        -- convert our 60 (or less) bits of hex to a 64-bit integer
        set inn=conv(substr(hash,
                off + 1, -- substr indexes are 1-based
                if(off, chu, len%chu) -- get 15 chars unless we're at the beginning of the string
            ), 16, 10 -- from base16 to base10
        );
        -- loop until we process all the bits in our chunk
        while inn > 0 do 
            set wrk = inn & 31; -- we're interested only in the last 5 bits
            set ret = concat(char(wrk + 48 -- '0'
                    + if(wrk<10,0,39)  -- 'a'
                    + (wrk>17) -- 'i'
                    + (wrk>19) -- 'l'
                    + (wrk>21) -- 'o'
                    + (wrk>26) -- 'u'
                ), ret);
            -- shift off those 5 bits we just handled
            set inn = inn >> 5;
        end while;
    end while;
    return ret;
end//


drop function if exists base32_decode//
create function base32_decode
    (hash varchar(255) character set latin1) 
    returns varchar(255) 
    no sql begin

    return hash;

end//

delimiter ;
select base32_encode('b35f2394eabe11e4b16d80e65018a9be') union all select '5kbwhs9tny27jb2vc0ws81hady';

