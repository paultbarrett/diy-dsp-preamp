# Using jacktrip on the client(s):

- start a jack server (or use pipewire - but change the server's sampling rate
  prop accordingly):

   ```
   SRATE=24000
   killall jackd
   [ $(pidof jackd) ] || jackd -d dummy -r $SRATE -P 0 -C 2`
   ```

- run jacktrip (+ discard `UDP 30ms` message flood)

   ```
   while [ 1 ]; do
           jacktrip -c remote 2>/dev/null
           sleep 1
   done
   ```

Alternatively, use pulseaudio to route audio through jack ; see the 
`misc/wrap_jack` script.

