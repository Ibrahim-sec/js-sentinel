import re
import json
import base64
import urllib.parse
import jsbeautifier
from typing import Dict, List, Tuple, Optional

class JavaScriptDeobfuscator:
    """Advanced JavaScript deobfuscation service with multiple techniques."""
    
    def __init__(self):
        self.deobfuscation_stats = {
            'hex_strings_decoded': 0,
            'unicode_strings_decoded': 0,
            'base64_strings_decoded': 0,
            'string_concatenations_resolved': 0,
            'eval_expressions_simplified': 0,
            'variable_substitutions': 0,
            'dead_code_removed': 0
        }
    
    def deobfuscate(self, js_content: str) -> Tuple[str, Dict]:
        """Main deobfuscation method that applies multiple techniques."""
        self.deobfuscation_stats = {key: 0 for key in self.deobfuscation_stats}
        
        # Step 1: Initial beautification
        deobfuscated = self._beautify_code(js_content)
        
        # Step 2: Decode encoded strings
        deobfuscated = self._decode_hex_strings(deobfuscated)
        deobfuscated = self._decode_unicode_strings(deobfuscated)
        deobfuscated = self._decode_base64_strings(deobfuscated)
        deobfuscated = self._decode_url_encoded_strings(deobfuscated)
        
        # Step 3: Resolve string concatenations
        deobfuscated = self._resolve_string_concatenations(deobfuscated)
        
        # Step 4: Simplify array access patterns
        deobfuscated = self._simplify_array_access(deobfuscated)
        
        # Step 5: Replace variable references with values
        deobfuscated = self._substitute_variables(deobfuscated)
        
        # Step 6: Simplify eval expressions
        deobfuscated = self._simplify_eval_expressions(deobfuscated)
        
        # Step 7: Remove dead code
        deobfuscated = self._remove_dead_code(deobfuscated)
        
        # Step 8: Resolve function calls with constant arguments
        deobfuscated = self._resolve_function_calls(deobfuscated)
        
        # Step 9: Clean up and final beautification
        deobfuscated = self._final_cleanup(deobfuscated)
        
        return deobfuscated, self.deobfuscation_stats
    
    def _beautify_code(self, code: str) -> str:
        """Beautify JavaScript code for better readability."""
        try:
            options = jsbeautifier.default_options()
            options.indent_size = 2
            options.max_preserve_newlines = 2
            options.wrap_line_length = 120
            options.break_chained_methods = True
            options.space_before_conditional = True
            return jsbeautifier.beautify(code, options)
        except Exception:
            return code
    
    def _decode_hex_strings(self, code: str) -> str:
        """Decode hexadecimal encoded strings."""
        def hex_replacer(match):
            try:
                hex_value = match.group(1)
                decoded = chr(int(hex_value, 16))
                self.deobfuscation_stats['hex_strings_decoded'] += 1
                return f'"{decoded}"' if decoded.isprintable() else match.group(0)
            except (ValueError, OverflowError):
                return match.group(0)
        
        # Pattern for \\x followed by 2 hex digits
        pattern = r'\\\\x([0-9a-fA-F]{2})'
        return re.sub(pattern, hex_replacer, code)
    
    def _decode_unicode_strings(self, code: str) -> str:
        """Decode Unicode encoded strings."""
        def unicode_replacer(match):
            try:
                unicode_value = match.group(1)
                decoded = chr(int(unicode_value, 16))
                self.deobfuscation_stats['unicode_strings_decoded'] += 1
                return decoded if decoded.isprintable() else match.group(0)
            except (ValueError, OverflowError):
                return match.group(0)
        
        # Pattern for \\u followed by 4 hex digits
        pattern = r'\\\\u([0-9a-fA-F]{4})'
        return re.sub(pattern, unicode_replacer, code)
    
    def _decode_base64_strings(self, code: str) -> str:
        """Decode Base64 encoded strings."""
        def base64_replacer(match):
            try:
                base64_string = match.group(1)
                decoded = base64.b64decode(base64_string).decode('utf-8')
                self.deobfuscation_stats['base64_strings_decoded'] += 1
                return f'"{decoded}"'
            except Exception:
                return match.group(0)
        
        # Pattern for atob("base64string") or btoa patterns
        patterns = [
            r'atob\\s*\\(\\s*["\']([A-Za-z0-9+/=]+)["\']\\s*\\)',
            r'window\\.atob\\s*\\(\\s*["\']([A-Za-z0-9+/=]+)["\']\\s*\\)'
        ]
        
        for pattern in patterns:
            code = re.sub(pattern, base64_replacer, code)
        
        return code
    
    def _decode_url_encoded_strings(self, code: str) -> str:
        """Decode URL encoded strings."""
        def url_replacer(match):
            try:
                url_string = match.group(1)
                decoded = urllib.parse.unquote(url_string)
                return f'"{decoded}"'
            except Exception:
                return match.group(0)
        
        # Pattern for decodeURIComponent or unescape
        patterns = [
            r'decodeURIComponent\\s*\\(\\s*["\']([^"\']+)["\']\\s*\\)',
            r'unescape\\s*\\(\\s*["\']([^"\']+)["\']\\s*\\)'
        ]
        
        for pattern in patterns:
            code = re.sub(pattern, url_replacer, code)
        
        return code
    
    def _resolve_string_concatenations(self, code: str) -> str:
        """Resolve simple string concatenations."""
        def concat_replacer(match):
            try:
                str1 = match.group(1)
                str2 = match.group(2)
                self.deobfuscation_stats['string_concatenations_resolved'] += 1
                return f'"{str1}{str2}"'
            except Exception:
                return match.group(0)
        
        # Pattern for "string1" + "string2"
        patterns = [
            r'"([^"]*?)"\s*\+\s*"([^"]*?)"',
            r"'([^']*?)'\s*\+\s*'([^']*?)'",
            r'"([^"]*?)"\s*\+\s*\'([^\']*?)\'',
            r"'([^']*?)'\s*\+\s*\"([^\"]*?)\""
        ]
        
        # Apply multiple passes to handle chained concatenations
        for _ in range(5):  # Limit iterations to prevent infinite loops
            original_code = code
            for pattern in patterns:
                code = re.sub(pattern, concat_replacer, code)
            if code == original_code:  # No more changes
                break
        
        return code
    
    def _simplify_array_access(self, code: str) -> str:
        """Simplify array access patterns like arr[0], arr[1], etc."""
        # This is a simplified version - a full implementation would need AST parsing
        
        # Pattern for simple array definitions followed by indexed access
        array_pattern = r'var\s+(\w+)\s*=\s*\[(.*?)\];'
        
        def process_array(match):
            var_name = match.group(1)
            array_content = match.group(2)
            
            # Parse array elements (simplified)
            try:
                elements = []
                for element in array_content.split(','):
                    element = element.strip()
                    if element.startswith('"') and element.endswith('"'):
                        elements.append(element[1:-1])
                    elif element.startswith("'") and element.endswith("'"):
                        elements.append(element[1:-1])
                    else:
                        elements.append(element)
                
                # Replace array access patterns
                access_pattern = f'{var_name}\\[(\\d+)\\]'
                
                def replace_access(access_match):
                    try:
                        index = int(access_match.group(1))
                        if 0 <= index < len(elements):
                            return f'"{elements[index]}"'
                    except (ValueError, IndexError):
                        pass
                    return access_match.group(0)
                
                # Apply replacements to the rest of the code
                nonlocal code
                code = re.sub(access_pattern, replace_access, code)
                
                return match.group(0)  # Keep original array definition for now
            except Exception:
                return match.group(0)
        
        re.sub(array_pattern, process_array, code)
        return code
    
    def _substitute_variables(self, code: str) -> str:
        """Substitute variables with their constant values."""
        # Pattern for variable assignments with string literals
        var_pattern = r'var\s+(\w+)\s*=\s*["\']([^"\']*)["\'];'
        
        variables = {}
        
        # Find variable assignments
        for match in re.finditer(var_pattern, code):
            var_name = match.group(1)
            var_value = match.group(2)
            variables[var_name] = var_value
        
        # Replace variable references
        for var_name, var_value in variables.items():
            # Only replace if it's a standalone variable reference
            pattern = f'\\b{re.escape(var_name)}\\b'
            replacement = f'"{var_value}"'
            
            # Count replacements
            original_code = code
            code = re.sub(pattern, replacement, code)
            if code != original_code:
                self.deobfuscation_stats['variable_substitutions'] += 1
        
        return code
    
    def _simplify_eval_expressions(self, code: str) -> str:
        """Simplify eval expressions where possible."""
        # Pattern for eval with string literals
        eval_pattern = r'eval\s*\(\s*["\']([^"\']*)["\']s*\)'
        
        def eval_replacer(match):
            try:
                eval_content = match.group(1)
                # Only replace if it's safe (no dynamic content)
                if not re.search(r'[+\-*/]|\w+\s*\(', eval_content):
                    self.deobfuscation_stats['eval_expressions_simplified'] += 1
                    return eval_content
            except Exception:
                pass
            return match.group(0)
        
        return re.sub(eval_pattern, eval_replacer, code)
    
    def _remove_dead_code(self, code: str) -> str:
        """Remove obvious dead code patterns."""
        # Remove empty statements
        code = re.sub(r';\s*;', ';', code)
        
        # Remove unreachable code after return statements (simplified)
        code = re.sub(r'return\s+[^;]+;\s*[^}]+(?=})', lambda m: m.group(0).split(';')[0] + ';', code)
        
        # Remove empty blocks
        code = re.sub(r'{\s*}', '', code)
        
        # Count dead code removal
        if ';;' not in code:
            self.deobfuscation_stats['dead_code_removed'] += 1
        
        return code
    
    def _resolve_function_calls(self, code: str) -> str:
        """Resolve function calls with constant arguments."""
        # This is a simplified version - would need more sophisticated analysis
        
        # Pattern for String.fromCharCode calls
        charcode_pattern = r'String\.fromCharCode\s*\(\s*(\d+(?:\s*,\s*\d+)*)\s*\)'
        
        def charcode_replacer(match):
            try:
                char_codes = [int(x.strip()) for x in match.group(1).split(',')]
                decoded = ''.join(chr(code) for code in char_codes if 0 <= code <= 1114111)
                return f'"{decoded}"'
            except Exception:
                return match.group(0)
        
        return re.sub(charcode_pattern, charcode_replacer, code)
    
    def _final_cleanup(self, code: str) -> str:
        """Final cleanup and beautification."""
        # Remove excessive whitespace
        code = re.sub(r'\n\s*\n\s*\n', '\n\n', code)
        
        # Remove trailing semicolons on empty lines
        code = re.sub(r'^\s*;\s*$', '', code, flags=re.MULTILINE)
        
        # Final beautification
        return self._beautify_code(code)
    
    def detect_obfuscation_type(self, code: str) -> Dict[str, bool]:
        """Detect the type of obfuscation used."""
        detection_results = {
            'hex_encoding': bool(re.search(r'\\x[0-9a-fA-F]{2}', code)),
            'unicode_encoding': bool(re.search(r'\\u[0-9a-fA-F]{4}', code)),
            'base64_encoding': bool(re.search(r'atob\s*\(', code)),
            'string_concatenation': bool(re.search(r'["\'][^"\']*["\']s*\+\s*["\']', code)),
            'array_obfuscation': bool(re.search(r'\w+\[\d+\]', code)),
            'eval_usage': bool(re.search(r'\beval\s*\(', code)),
            'function_obfuscation': bool(re.search(r'String\.fromCharCode', code)),
            'variable_name_obfuscation': bool(re.search(r'\b[a-zA-Z_$][a-zA-Z0-9_$]{0,2}\b', code)),
            'high_entropy': len(set(code)) / len(code) > 0.1 if code else False,
            'packed_code': 'eval(function(p,a,c,k,e,d)' in code,
            'jsfuck_style': bool(re.search(r'[\[\]()!+]{10,}', code))
        }
        
        return detection_results
    
    def get_obfuscation_score(self, code: str) -> float:
        """Calculate an obfuscation score from 0 (not obfuscated) to 1 (heavily obfuscated)."""
        if not code:
            return 0.0
        
        score = 0.0
        
        # Check for various obfuscation indicators
        indicators = [
            (r'\\x[0-9a-fA-F]{2}', 0.2),  # Hex encoding
            (r'\\u[0-9a-fA-F]{4}', 0.2),  # Unicode encoding
            (r'atob\s*\(', 0.15),  # Base64 decoding
            (r'\beval\s*\(', 0.25),  # Eval usage
            (r'String\.fromCharCode', 0.15),  # Character code conversion
            (r'[\[\]()!+]{10,}', 0.3),  # JSFuck-style
            (r'eval\(function\(p,a,c,k,e,d\)', 0.4),  # Packed code
        ]
        
        for pattern, weight in indicators:
            if re.search(pattern, code):
                score += weight
        
        # Check entropy (randomness)
        if len(code) > 100:
            unique_chars = len(set(code))
            entropy_score = min(unique_chars / 50, 1.0)  # Normalize to 0-1
            score += entropy_score * 0.2
        
        # Check for very short variable names (common in obfuscation)
        short_vars = len(re.findall(r'\b[a-zA-Z_$][a-zA-Z0-9_$]{0,2}\b', code))
        total_vars = len(re.findall(r'\b[a-zA-Z_$][a-zA-Z0-9_$]*\b', code))
        if total_vars > 0:
            short_var_ratio = short_vars / total_vars
            score += short_var_ratio * 0.15
        
        return min(score, 1.0)  # Cap at 1.0

# Global instance
deobfuscator = JavaScriptDeobfuscator()

