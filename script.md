[Keyboard clacking]

I like `jq`.

It's a beautifully simple tool. It formats my garbage json.

```bash
echo '{"action": "Work it","metric": "Harder","process": "Make it","optimization": "Better","execution": "Do it","velocity": "Faster","outcome": "Makes us stronger","schedule": {"frequency": "More than ever","interval": "Hour after hour","is_finished": false,"status": "Our work is never over"}}' | jq
```

It's a wonderful convenience, letting me select just what I want

```bash
echo '["react", "rails", "ember", "angular", "vue", "svelte", "IIS", "htmx"]' | jq -r '.[7]'
```

And it sprinkles in just the right amount control allowing me to update just the small things that I need to.

```bash
echo '{"amplifier": {"gain": 10}}' | jq '.amplifier.gain += 1'
```

> Theodore: 
> ...jq being practically a programming language (it’s probably Turing complete?)

Wait, what?

> [Brief aside: Turing]

When we say something is *Turing complete*, we mean it can compute anything that a Turing machine can—that is, given enough time and space, it can simulate any well-defined algorithm. Alan Turing gave us a minimal model: a strip of tape, a head that reads and writes symbols, and a small set of rules that say "if you're in this state and you see this symbol, write that, move left or right, and go to that state." If a system can emulate that, it can run any computation. No infinite loops required for the *definition*—we're just saying the *language* or *machine* is powerful enough.

A nice way to see that power without building a literal tape is *Rule 110*. It's a one-dimensional cellular automaton: you have a row of cells, each on or off. One simple rule decides the next row. For each cell you look at three neighbours—left, self, right—and the rule says: 111→0, 110→1, 101→1, 100→0, 011→1, 010→1, 001→1, 000→0. That's it. You start with a single "on" cell and step the rule over and over. The pattern that grows is chaotic, persistent, and it turns out *Rule 110 is Turing complete*. So this tiny rule, applied to a line of cells, can—in principle—compute anything. We'll use Rule 110 as our running example: if we can run it in jq, we're in the same league.

[Keyboard clacking]

```
jq -n '"Hello World"'
```


[Keyboard clacking]

```
jq -n '
  def greet(name): "Hello, \(name)!";
  
  greet("Zach")
```


[Keyboard clacking]

```
jq -n 'range(1, 101) | if . % 15 == 0 then "FizzBuzz" elif . % 3 == 0 then "Fizz" elif . % 5 == 0 then "Buzz" else . end'
```

Oh no... 

> fade to black...

So there's been one thing that I've always yearned for. The simplicity of `jq` for yet another markup language that I've come to dread. One that combines the low level efficiency of `javascript` and the spacing conviction of Guido van Rossum. 

YAML, which stands for "YAML Ain't Markup Language".

Wouldn't be nice if `jq` could just solve the problem of world YAML.

> [Keyboard clacking] and scrolling test suite. Fade to black.

Our first stop is checking for dealbreakers, and it's about time to talk about `functional programming`.

> [Attanborough voice]

Functional programming is concerned with describing a process instead of describing a thing.
Balls can bounce, people walk, and programmers refactor.

Chaining processes together allows you to quickly describe complex processes.

```
ball.bounce().paint("red").bounce().paint("blue")
```

Critically, functional eschews "side effects". Providing an input always yields the same output.

> [Zach voice]

So `jq` is functional, and on purpose doesn't provide a few things we need to do our job.

For example, we can't connect to a port, read a file, or save a file. Not a big deal, but we'll have to provide some glue.

So no dealbreakers. Let's build this.

```jq
def parse_yaml:
  (if type == "string" then . else "" end) as $raw
  | $raw | slog("debug"; "parse_yaml_start"; {"lines": ($raw | split("\n") | length)})
```

First we make sure we've got a real input, then we split it into lines that we can work with

```
  | parsed_lines as $lines
  | reduce $lines[] as $line (
      { stack: [{obj: {}, indent: -1, key: null}], last_key: null, root_is_list: false, block_scalar: null, anchors: {} };
      _process_line($line)
    )
```
We then walk through all of our lines "reducing" them into a single object, and flagging a few characteristics
that we'd need to pay attention to that would change what the line would look like,
and we just "process" the line.

```
  | (if .block_scalar != null then _finalize_block else . end)
  | if .root_is_list then .stack[1].obj + [.stack[0].obj] else .stack[.stack | length - 1].obj end;
```

Then this bit glues it back together for us. Well, that's right, we're done...
Well, what's the processing bit?

Well, it breaks down into a flow like this:

1. The "State" Check (Context)Before looking at the content, the code asks: "Are we in the middle of a multi-line string (Block Scalar)?"If Yes: Just keep grabbing text until the indentation breaks.If No: Move to the next step.
2. The "Depth" Check (Indentation)The code looks at the leading spaces.Going Deeper: If indentation increased, it pushes a new "folder" onto the Stack.Going Back: If indentation decreased, it "pops" the current folder and saves it into the parent above it.
3. The "Structural" Check (List vs. Object)Now it looks at the character after the indentation:Starts with -: It's a List Item. Add this to the current array.Starts with key:: It's an Object.Starts with & or *: It’s an Anchor (save for later) or a Reference (copy from earlier).
4. The "Data" Check (Typing/Coercion)Finally, it looks at the actual value (e.g., true, 123, or "hello").The code calls coerce_value. This is where it decides:123 $\rightarrow$ Integer123.45 $\rightarrow$ Floattrue/false $\rightarrow$ BooleanAnything else $\rightarrow$ String

And when all thats done it looks something like this:

```bash
echo "mykey: myvalue" | jq -R -s -rf run.jq 
# {"mykey": "myvalue"}
```

Well, that's a great result, albeit a little simple — it's not like you can...

```bash
jq -R -s -rf run.jq << EOF

defaults: &defaults
  host: bevel.work
  port: 443
mylist: 
  - "a"
  - true
  - 1.0
dev:
  <<: *defaults
  port: 8080

EOF | jq .dev.host
```

Wow, but how will people know. What we've accomplished here. We need a way for 
people to react to such a momentus event. If only we could...

```
<title>jqyml – YAML to JSON</title>
<Head />
<body>
    <Header />
    <div class="counter-box">
        Visitor count: <span id="count" class="count">
        <If count_is_zero>No visitors</If>
        <If count_gt_0>{count}</If></span>
    </div>
<-- snip -->
</body>
```

No, stop. No one needs this. Just because you could build it with jq, doesn't mean
you should create a cheap "jqx" wrapper...

> Navigate to jq.bevel.work

So now we parse pesky YAML files in the style and simplicity of `jq`.
If you'd like to be one of the few to play with it I encourage you go to `http://jq.bevel.work`
before someone figures out how to get my Regex to explode.

After that point code is available on Github.
